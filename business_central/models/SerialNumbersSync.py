from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback


class SerialNumberSyncLogs(models.Model):
    _name = 'business_central.serial_number_logs'
    _description = "Serial Number Sync Logs"
    _order = 'id desc'
    
    name = fields.Text("Message")
    message = fields.Text("Description")
    ref = fields.Text("References")
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

    def _sns_get_process_logs(self):
        return self.env.ref("business_central.action_serial_number_sync_logs").read()[0]

class SerialNumberSync(models.Model):
    _inherit = 'business_central.sale_order_line_staging'

    name = fields.Char("Name")
    bc_sns_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], "Serial Number Status", default='pending')
    bc_production_lots = fields.Many2many("stock.production.lot", string="Serial Numbers",relation='staging_line_lot_rel')
    bc_product_id = fields.Many2one("product.product", string="Product")
    bc_sale_line_id = fields.Many2one("sale.order.line","Order Line")
    bc_quantity_delivered = fields.Float("Quantity Delivered")
    bc_installation_required = fields.Boolean("Installation Required",compute="_compute_installation_required",store=True)

    @api.depends('bc_product_id')
    def _compute_installation_required(self):
        for line in self:
            line.bc_installation_required = line.bc_product_id and line.bc_product_id.snet_installation_required or False

    def _sns_run_process(self, debug_mode = False):
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            total_records = self.sudo().search_count([('bc_sns_state','in',['pending','fail'])])
            pages = int(total_records/80) +1 
            
            for page in range(0, pages):
                records = self.sudo().search([('bc_sns_state','in',['pending','fail'])], limit = 80, offset = page*80)
                try:
                    rec_filter = ' or '.join(["(OrderNo eq '%s')"%(x.DocNo) for x in records])
                    url = '%s/shipmentdetails?$filter=(%s)&$expand=serialdetails'%(base_url, rec_filter)
                    response = requests.get(url, auth=token, headers=headers)
                    if response and response.ok:
                        data = response.json()
                        stocks = data['value'] or list()
                        for stock in stocks:
                            order_line = records.filtered(lambda x: x.LineNo == str(stock['OrderLineNo']) and x.DocNo == stock['OrderNo'])
                            try:
                                if order_line:
                                    has_serial_numbers = any(filter(lambda x: x['SerialNo'] ,stock['serialdetails']))
                                    order_line.bc_quantity_delivered = stock['Quantity']

                                    if order_line.bc_product_id and has_serial_numbers:
                                        existing_serial_numbers = order_line.bc_production_lots.mapped('name')
                                        order_line.write({
                                            'bc_production_lots': [(0,0,{
                                                'name':serial_number['SerialNo'],
                                                'product_id':order_line.bc_product_id.id,
                                                'product_uom_id':order_line.bc_product_id.uom_id.id,
                                                'company_id': order_line.order_id.sale_order.company_id.id
                                                }
                                            ) 
                                        for serial_number in 
                                        filter(lambda x: x['SerialNo'] not in existing_serial_numbers, 
                                        stock['serialdetails'])]})
                                    
                                    order_line.bc_sns_state = 'done'
                                else:
                                    raise Exception("Document %s with Line %s not found"%(stock['OrderNo'], stock['OrderLineNo']))
                            except Exception as e:
                                order_line.write({'bc_sns_state': 'fail'})
                                self.env['business_central.serial_number_logs']._log_error('Error while Syncing Records', str(e), ','.join(order_line.mapped('name')), debug_mode and traceback.format_exc() or '', debug_mode)    
                    else:
                        raise Exception(response.text)
                except Exception as e:
                    records.write({'bc_sns_state': 'fail'})
                    self.env['business_central.serial_number_logs']._log_error('Error while Syncing Records', str(e), ','.join(records.mapped('name')), debug_mode and traceback.format_exc() or '', debug_mode)
        except Exception as e:
            self.env['business_central.serial_number_logs']._log_error('Error while Syncing Records', str(e), '', debug_mode and traceback.format_exc() or '', debug_mode)
            

    def _cron_serail_number_sync(self):
        self._sns_run_process()

    def _sns_pending_records(self):
        return self.search_count([('bc_sns_state','in',['pending'])])

    def _sns_failed_records(self):
        return self.search_count([('bc_sns_state','in',['fail'])])
    
    def _sns_done_records(self):
        return self.search_count([('bc_sns_state','in',['done'])])
    
    def _sns_total_records(self):
        return self.search_count([])
    
    def _sns_get_final_records(self):
        return self.env.ref('business_central.action_serial_number_sync_final').read()[0]

    def _sns_get_pending_records(self):
        return self.env.ref('business_central.action_serial_number_sync_pending').read()[0]
    
    def _sns_get_all_records(self):
        return self.env.ref('business_central.action_serial_number_sync').read()[0]

    def _sns_get_processed_records(self):
        return self.env.ref('business_central.action_serial_number_sync_done').read()[0]

    def _sns_get_failed_records(self):
        return self.env.ref('business_central.action_serial_number_sync_failed').read()[0]
