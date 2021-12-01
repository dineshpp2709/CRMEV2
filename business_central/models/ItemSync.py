# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

Type = {
    'consu': 'Non-Inventory',
    'service': 'Service',
    'product': 'Inventory'
}

class ProductSyncLogs(models.Model):
    _name = 'business_central.product_logs'
    _description = "Product Sync Logs"
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

    def _ps_get_process_logs(self):
        return self.env.ref("business_central.action_product_sync_logs").read()[0]

class ProductSync(models.Model):
    
    _inherit = 'product.template'

    bc_ps_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_ps_system_id = fields.Char("Item System Id")
    
    def write(self, vals):
        vals['bc_ps_state'] = vals.get('bc_ps_state','pending')
        return super(ProductSync, self).write(vals)

    def _ps_run_process(self, debug_mode = False):
        products = self.sudo().search([('bc_ps_state','in',['pending','fail']),('snet_item_code','!=',False)])
        try:
            data_transfor = (lambda x: {
                "ItemCode" : x.snet_item_code[0:20],
                "Description" : x.name and x.name[0:100] or '',
                "Description2" : x.name and x.name[100:150] or '',
                "UOMCode" : x.uom_id and x.uom_id.snet_uom_code[0:10] or '',
                "ItemType" : Type.get(x.type,''),
                "ItemCategory" : x.categ_id and x.categ_id.snet_product_category_code[0:20] or '',
                "GenProdPostingGroup" : x.snet_prod_posting and x.snet_prod_posting.code[0:20] or '',
                "InvPostGrp" : x.snet_inv_posting and x.snet_inv_posting.code[0:20] or '',
                "Blocked" : x.snet_blocked,
                "GSTGroupCode" : x.taxes_id and x.taxes_id[0].snet_customer_tax_code[0:10] or '',
                "HSNCode" : x.l10n_in_hsn_code and x.l10n_in_hsn_code[0:10] or '',
                "Exempted" : x.snet_exempted,
                "SerialTracking" : x.tracking and bool(x.tracking == 'serial'),
                "product": x
            })
            
            transformed_data = [data_transfor(x) for x in products]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
                    
            for record in transformed_data:
                try:
                    url = '%s/item'%(base_url)
                    product = record.pop('product')
                    headers.pop('If-Match', False)
                    
                    if product.bc_ps_system_id:
                        url = "%s(ItemCode='%s')"%(url, record['ItemCode'])
                        headers['If-Match'] = '*'
                        record.pop('ItemCode',False)
                        response = requests.patch(url, data=json.dumps(record), auth=token, headers=headers)
                    else:    
                        response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        product.bc_ps_system_id = data['SystemId']
                        product.bc_ps_state = 'done'
                    else:
                        product.bc_ps_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.product_logs']._log_error('Error while Syncing Record', str(e), product.snet_item_code, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            products.write({'bc_ps_state': 'fail'})
            self.env['business_central.product_logs']._log_error('Error while Syncing Records', str(e), ','.join(products.mapped('snet_item_code')), debug_mode and traceback.format_exc() or '', debug_mode)
    
    def _cron_product_sync(self):
        self._ps_run_process()

    def _ps_pending_records(self):
        return self.search_count([('bc_ps_state','in',['pending']),('snet_item_code','!=',False)])

    def _ps_failed_records(self):
        return self.search_count([('bc_ps_state','in',['fail']),('snet_item_code','!=',False)])
    
    def _ps_done_records(self):
        return self.search_count([('bc_ps_state','in',['done']),('snet_item_code','!=',False)])
    
    def _ps_total_records(self):
        return self.search_count([('snet_item_code','!=',False)])
    
    def _ps_get_final_records(self):
        return self.env.ref('business_central.action_product_sync_final').read()[0]

    def _ps_get_pending_records(self):
        return self.env.ref('business_central.action_product_sync_pending').read()[0]
    
    def _ps_get_all_records(self):
        return self.env.ref('business_central.action_product_sync').read()[0]

    def _ps_get_processed_records(self):
        return self.env.ref('business_central.action_product_sync_done').read()[0]

    def _ps_get_failed_records(self):
        return self.env.ref('business_central.action_product_sync_failed').read()[0]
    
