# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class SaleOrderSyncLogs(models.Model):
    _name = 'business_central.sale_order_logs'
    _description = "Sale Order Sync Logs"
    _order = 'id desc'
    
    name = fields.Char("Message")
    message = fields.Char("Description")
    ref = fields.Char("References")
    active = fields.Boolean("Active", default=True)
    request = fields.Text("Request")
    debug_mode = fields.Boolean("Debug Mode")

    def _log_error(self, short_message, message, ref, request='', mode=False):
        self.sudo().create({
            'name': short_message,
            'message': message,
            'ref': ref,
            'request': request,
            'debug_mode': mode
        })

    def _sos_get_process_logs(self):
        return self.env.ref("business_central.action_sale_order_sync_logs").read()[0]

class SaleOrderStaging(models.Model):
    _name = 'business_central.sale_order_staging'
    _description = "Sale Order Staging"
    _rec_name = "OrderNo"
    _order = 'id desc'

    DocumentType = fields.Char("Document Type")
    OrderNo = fields.Char("Order No")
    CustomerNo = fields.Char("Customer No")
    OrderDate = fields.Char("Order Date")
    LocationCode = fields.Char("Location Code")
    Salesperson = fields.Char("Sales person")
    PaymentTerms = fields.Char("Payment Terms")
    CustReference = fields.Char("Customer Reference")
    GSTType = fields.Char("GSTType")
    CurrencyCode = fields.Char("Currency Code")
    NoOfLines = fields.Integer("No Of Lines")
    LineAmountTotal = fields.Float("Amount Total")
    FinRegion = fields.Char("Region")
    FinCostCentre = fields.Char("Cost Centre")
    FinPractice = fields.Char("Practice")
    FinBusiness = fields.Char("Business")
    FinBranch = fields.Char("Branch")
    FinZone = fields.Char("Zone")
    FinCentre = fields.Char("Centre")
    saleslines = fields.One2many("business_central.sale_order_line_staging","order_id","Order Lines", ondelete="cascade")
    
    sale_order = fields.Many2one("sale.order","Order", required=True)
    delivery_address = fields.Many2one("res.partner", "Delivery Address")
    helpdesk_ticket = fields.Many2one("helpdesk.ticket","Ticket")
    
    bc_sos_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending', string="Status")
    
    def _prepare_api_data(self):
        line_transform = (lambda x: {
            "DocType": x.DocType,
            "DocNo": x.DocNo,
            "LineNo": x.LineNo,
            "LineType": x.LineType,
            "ItemNo": x.ItemNo,
            "Description" : x.Description,
            "Quantity" : x.Quantity,
            "UOM": x.UOM,
            "UnitPrice" : x.UnitPrice,
        })

        data_transform = (lambda x: {
                "DocumentType" : x.DocumentType,
                "OrderNo" : x.OrderNo,
                "CustomerNo" : x.CustomerNo,
                "OrderDate" : x.OrderDate,
                "LocationCode" : x.LocationCode,
                "Salesperson" : x.Salesperson,
                "PaymentTerms" : x.PaymentTerms,
                "CustReference" : x.CustReference,
                "GSTType" : x.GSTType,
                "CurrencyCode" : x.CurrencyCode,
                "NoOfLines" : x.NoOfLines,
                "LineAmountTotal" : x.LineAmountTotal,
                "FinRegion" : x.FinRegion,
                "FinCostCentre" : x.FinCostCentre,
                "FinPractice" : x.FinPractice,
                "FinBusiness" : x.FinBusiness,
                "FinBranch" : x.FinBranch,
                "FinZone" : x.FinZone,
                "saleslines": [line for line in map(line_transform, x.saleslines)],
                'order': x,
            })
        return [x for x in map(data_transform, self)]

    def _sos_run_process(self, debug_mode = False):
        orders = self.sudo().search([('bc_sos_state','in',['pending','fail'])])
        try:
            transformed_data = orders._prepare_api_data()

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            url = '%s/salesorders'%(base_url)
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
                    
            for record in transformed_data:
                try:
                    order = record.pop('order')
                    response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        order.bc_sos_state = 'done'
                    else:
                        order.bc_sos_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.sale_order_logs']._log_error('Error while Syncing Record', str(e), order.OrderNo, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            orders.write({'bc_sos_state': 'fail'})
            self.env['business_central.sale_order_logs']._log_error('Error while Syncing Records', str(e), ','.join(orders.mapped('OrderNo')), debug_mode and traceback.format_exc() or '', debug_mode)
    
    def _cron_sale_order_sync(self):
        self._sos_run_process()

    def _cron_case_generation(self):
        for order in self.search([('helpdesk_ticket','=',False)]):
            if any(order.saleslines.mapped('bc_installation_required')) and sum(order.saleslines.mapped('Quantity')) == sum(order.saleslines.mapped('bc_quantity_delivered')):
                team = self.env['helpdesk.team'].sudo().search([('use_fsm', '=', True)], limit=1)
                project = self.env['project.project'].sudo().search([('is_fsm', '=', True)], limit=1)
                location = self.env['stock.warehouse'].sudo().search([('code','=',order.LocationCode)], limit=1)
                if team and project and location:
                    ticket = self.env['helpdesk.ticket'].sudo().create({
                        'name': order.sale_order.name,
                        'team_id': team.id,
                        'partner_id': order.sale_order.partner_id.id,
                        'snet_location': location.id,
                        'snet_delivery_address': order.sale_order.partner_shipping_id.id
                    })
                    order.helpdesk_ticket = ticket.id
                    for lot in order.saleslines.mapped('bc_production_lots'):
                        self.env['project.task'].sudo().create({
                            'name': ticket.name,
                            'helpdesk_ticket_id': ticket.id,
                            'project_id': project.id,
                            'partner_id': ticket.partner_id.id,
                            'snet_production_lots': lot.id,
                            'snet_product_id': lot.product_id.id
                        })
                elif not team:
                    raise UserError(_('Team not created for Installation Tickets.'))
                elif not project:
                    raise UserError(_('Field Service Project not created.'))
                elif not location:
                    raise UserError(_('Location not found.'))

    def _sos_pending_records(self):
        return self.search_count([('bc_sos_state','in',['pending'])])

    def _sos_failed_records(self):
        return self.search_count([('bc_sos_state','in',['fail'])])
    
    def _sos_done_records(self):
        return self.search_count([('bc_sos_state','in',['done'])])
    
    def _sos_total_records(self):
        return self.search_count([])
    
    def _sos_get_final_records(self):
        return self.env.ref('business_central.action_sale_order_sync_final').read()[0]

    def _sos_get_pending_records(self):
        return self.env.ref('business_central.action_sale_order_sync_pending').read()[0]
    
    def _sos_get_all_records(self):
        return self.env.ref('business_central.action_sale_order_sync').read()[0]

    def _sos_get_processed_records(self):
        return self.env.ref('business_central.action_sale_order_sync_done').read()[0]

    def _sos_get_failed_records(self):
        return self.env.ref('business_central.action_sale_order_sync_failed').read()[0]
        
class SaleOrderLineStaging(models.Model):
    _name = 'business_central.sale_order_line_staging'
    _description = "Sale Order Line Staging"
    _order = 'id desc'

    order_id = fields.Many2one("business_central.sale_order_staging","Order Id", required=True, ondelete="cascade")
    DocType = fields.Char("Doc Type")
    DocNo = fields.Char("Doc No")
    LineNo = fields.Char("Line No")
    LineType = fields.Char("Line Type")
    ItemNo = fields.Char("Item No")
    Description = fields.Char("Description")
    Quantity = fields.Float("Quantity")
    UOM = fields.Char("UOM")
    UnitPrice = fields.Float("UnitPrice")
    