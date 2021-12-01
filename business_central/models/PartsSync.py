from requests import auth
from odoo import api, fields, models
from itertools import groupby

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class PartSyncLogs(models.Model):
    _name = 'business_central.parts_logs'
    _description = "Parts Sync Logs"
    _order = 'id desc'
    
    name = fields.Char("Message")
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

    def _ps_get_process_logs(self):
        return self.env.ref("business_central.action_part_sync_logs").read()[0]

class PartsSync(models.Model):
    _inherit = 'stock.production.lot'

    def _ps_run_process(self, debug_mode = False):
        try:
            serial_numbers = self.sudo().search([])
            product_model = self.env['product.product'].sudo()
            location_model = self.env['stock.warehouse'].sudo()

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            url = '%s/serviceinventory'%(base_url)	
            response = requests.get(url, auth=token, headers=headers)
            
            if response and response.ok:
                serial_numbers.write({'snet_available_stock':False})
                data = response.json()
                for lot in data.get('value',[]):
                    try:
                        serial_number = self.sudo().search([('name','=',lot.get('serialNo','')),('product_id.snet_item_code','=',lot.get('itemNo','')),('snet_location.code','=',lot.get('locationcode',''))], limit=1)
                        if serial_number:
                            serial_number.snet_available_stock = True
                        else:
                            product = product_model.search([('snet_item_code','=',lot.get('itemNo',''))], limit=1)
                            location = location_model.search([('code','=',lot.get('locationcode',''))], limit=1)
                            if product and location:
                                self.sudo().create({
                                    'company_id': self.env.company.id,
                                    'product_id': product.id,
                                    'snet_location': location.id,
                                    'snet_available_stock': True,
                                    'name': lot.get('serialNo','')
                                })
                            elif not product:
                                raise Exception("Product '%s' not found in system."%(lot.get('itemNo','')))
                            elif not location:
                                raise Exception("Location '%s' not found in system."%(lot.get('locationcode','')))
                    except Exception as e:
                        self.env['business_central.parts_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
            else:
                raise Exception(response.text)
        
        except Exception as e:        
            self.env['business_central.parts_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
                        
                
            
    def _cron_parts_sync(self):
        self._ps_run_process()

    def _ps_total_records(self):
        return self.search_count([])
    
    
    def _ps_get_all_records(self):
        return self.env.ref('business_central.action_part_sync').read()[0]

    