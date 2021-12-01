from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

GSTTypes = {
    "regular": 'Registered',
    "unregistered": 'Unregistered',
    "overseas": 'Export',
    "deemed_export": 'Deemed Export',
    "consumer": 'Exempted',
    "special_economic_zone": 'SEZ Development',
}

class PurchaseOrderSyncLogs(models.Model):
    _name = 'business_central.purchase_order_logs'
    _description = "Purchase Order Sync Logs"
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

    def _pos_get_process_logs(self):
        return self.env.ref("business_central.action_purchase_order_sync_logs").read()[0]

class PurchaseOrderSync(models.Model):
    _inherit = 'purchase.order'

    bc_pos_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_pos_system_id = fields.Char("PO System Id")

    def _pos_run_process(self, debug_mode = False):
        orders = self.sudo().search([('partner_id.snet_vendor_code','!=',False),('state','in',['done','purchase']),('bc_pos_state','in',['pending','fail'])])
        try:
            line_transfor = (lambda line, x: {
                "DocType": 'Order',
                "DocNo": x.order_id.name and x.order_id.name[0:20] or '',
                "LineNo": line,
                "LineType": 'Item',
                "ItemNo": x.product_id and x.product_id.snet_item_code[0:10] or '',
                "Description" : x.product_id and x.product_id.name and x.product_id.name[0:100] or '',
                "Quantity" : x.product_qty,
                "UOM": x.product_uom and x.product_uom.snet_uom_code[0:10],
                "UnitCost" : x.price_unit
            })

            data_transfor = (lambda x: {
                "DocumentType" : 'Order',
                "OrderNo" : x.name and x.name[0:20] or '',
                "VendorNo" : x.partner_id and x.partner_id.snet_vendor_code[0:20] or '',
                "POType": x.snet_purchase_type or '',
                "OrderDate" : x.date_order and x.date_order.strftime("%Y-%m-%d"),
                "LocationCode" : x.snet_location_id and x.snet_location_id.code[0:10] or '',
                "Purchaser" : x.user_id and x.user_id.snet_salesperson_code[0:20] or '',
                "PaymentTerms" : x.payment_term_id and x.payment_term_id.snet_payment_term_code[0:10] or '',
                "QuoteNo" : x.origin and (list(x.origin.split(','))[0])[0:20] or '',
                # "GSTType" : GSTTypes.get(x.l10n_in_gst_treatment,'') or '',
                "CurrencyCode" : x.currency_id and x.currency_id.name[0:10] or '',
                "ModeOfPurchase": x.snet_purchase_mode and x.snet_purchase_mode.code[0:10] or "",
                "WarrantyDetails": x.snet_warranty_details and x.snet_warranty_details[0:1000] or "",
                "PriceBasis": x.snet_price_basis and x.snet_price_basis.code[0:10] or "",
                "Freight": x.snet_freight and x.snet_freight.code[0:10] or "",
                "PaymentMode": x.snet_payment_mode and x.snet_payment_mode[0:10] or "",
                "ExpiryDate": x.snet_validity and x.snet_validity.strftime("%Y-%m-%d") or "0001-01-01",
                "DispatchMode": x.snet_dispatch_mode and x.snet_dispatch_mode[0:10] or "",
                "VendorQuoteNo": x.snet_vendor_ref and x.snet_vendor_ref[0:50] or "",
                "VendorQuoteDate": "0001-01-01",
                "ExpectedDate": x.snet_expected_delivery_date and x.snet_expected_delivery_date.strftime("%Y-%m-%d") or "0001-01-01",
                "NoOfLines" : x.order_line and len(x.order_line) or 0,
                "LineAmountTotal" : x.amount_untaxed,
                "FinRegion" : x.snet_fin_region and x.snet_fin_region.code[0:20] or '',
                "FinCostCentre" : x.snet_fin_cost_center and x.snet_fin_cost_center.code[0:20] or '',
                "FinPractice" : x.snet_fin_practice and x.snet_fin_practice.code[0:20] or '',
                "FinBusiness" : x.snet_fin_business and x.snet_fin_business.code[0:20] or '',
                "FinBranch" : x.snet_fin_branch and x.snet_fin_branch.code[0:20] or '',
                "FinZone" : x.snet_fin_zone and x.snet_fin_zone.code[0:20] or '',
                "purchlines": [line_transfor(lineno, line) for lineno, line in enumerate(x.order_line,1000)],
                "order": x
            })
            
            transformed_data = [data_transfor(x) for x in orders]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            url = '%s/purchaseorders'%(base_url)
            token = HTTPBasicAuth(username, password)
            for record in transformed_data:
                try:
                    order = record.pop('order')
                    
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        order.bc_pos_system_id = data['SystemId']
                        order.bc_pos_state = 'done'
                    else:
                        order.bc_pos_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.purchase_order_logs']._log_error('Error while Syncing Record', str(e), order.name, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            orders.write({'bc_pos_state': 'fail'})
            self.env['business_central.purchase_order_logs']._log_error('Error while Syncing Records', str(e), ','.join(orders.mapped('name')), debug_mode and traceback.format_exc() or '', debug_mode)

    def _cron_purchase_order_sync(self):
        self._pos_run_process()

    def _pos_pending_records(self):
        return self.search_count([('partner_id.snet_vendor_code','!=',False),('state','in',['done','purchase']),('bc_pos_state','in',['pending'])])

    def _pos_failed_records(self):
        return self.search_count([('partner_id.snet_vendor_code','!=',False),('state','in',['done','purchase']),('bc_pos_state','in',['fail'])])
    
    def _pos_done_records(self):
        return self.search_count([('partner_id.snet_vendor_code','!=',False),('state','in',['done','purchase']),('bc_pos_state','in',['done'])])
    
    def _pos_total_records(self):
        return self.search_count([('partner_id.snet_vendor_code','!=',False),('state','in',('purchase', 'done'))])
    
    def _pos_get_final_records(self):
        return self.env.ref('business_central.action_purchase_order_sync_final').read()[0]

    def _pos_get_pending_records(self):
        return self.env.ref('business_central.action_purchase_order_sync_pending').read()[0]
    
    def _pos_get_all_records(self):
        return self.env.ref('business_central.action_purchase_order_sync').read()[0]

    def _pos_get_processed_records(self):
        return self.env.ref('business_central.action_purchase_order_sync_done').read()[0]

    def _pos_get_failed_records(self):
        return self.env.ref('business_central.action_purchase_order_sync_failed').read()[0]
