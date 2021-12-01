# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class AvailableStockSyncLogs(models.Model):
    _name = 'business_central.available_stock_logs'
    _description = "Available Stock Sync Logs"
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

    def _ss_get_process_logs(self):
        return self.env.ref("business_central.action_available_stock_sync_logs").read()[0]


class AvailableStockSync(models.Model):
    _inherit = 'school_net.available_stock'

    bc_ss_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending', string="Status")

    def _ss_run_process(self, debug_mode = False):
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            try:
                url = '%s/ItemQty'%(base_url)
                response = requests.get(url, auth=token, headers=headers)
                if response and response.ok:
                    data = response.json()
                    for res in data['value']:
                        try:
                            stock_exist = self.sudo().search([('snet_product_code','=',res['no']),('snet_location_code','=',res['LocationCode'])])
                                
                            if not stock_exist:
                                
                                product = self.env['product.template'].sudo().search([('snet_item_code','=',res['no'])], limit=1)
                                location = self.env['stock.warehouse'].sudo().search([('code','=',res['LocationCode'])], limit=1)
                            
                                if product and location:
                                    self.sudo().create({
                                        'snet_product_id': product.id,
                                        'snet_product_code': res['no'],
                                        'snet_product_description': res['description'],
                                        'snet_location_id': location.id,
                                        'snet_location_code': res['LocationCode'],
                                        'snet_qty_in_hand': res['AvailableQty'],
                                    })
                                elif not product:
                                    raise Exception("Product '%s' received from Business Central is not available in System."%(res['description']))
                                elif not location:
                                    raise Exception("Location '%s' received from Business Central is not available in System."%(res['LocationCode']))
                                    
                            else:
                                stock_exist.sudo().write({
                                        'snet_qty_in_hand': res['AvailableQty'],
                                    })
                        except Exception as e:
                            self.env['business_central.available_stock_logs']._log_error('Error while posting record', str(e), res['description'], debug_mode and '%s'%(url) or '', debug_mode)
                else:
                    raise Exception(response.text)
            except Exception as e:
                self.env['business_central.available_stock_logs']._log_error('Error while Syncing Record', str(e), '', debug_mode and '%s'%(url) or '', debug_mode)
        except Exception as e:
            self.env['business_central.available_stock_logs']._log_error('Error while Syncing Records', str(e), '', debug_mode and traceback.format_exc() or '', debug_mode)

    def _cron_available_stock_sync(self):
        self._ss_run_process()

    def _ss_pending_records(self):
        return self.search_count([('bc_ss_state','in',['pending'])])

    def _ss_failed_records(self):
        return self.search_count([('bc_ss_state','in',['fail'])])
    
    def _ss_done_records(self):
        return self.search_count([('bc_ss_state','in',['done'])])
    
    def _ss_total_records(self):
        return self.search_count([])
    
    def _ss_get_final_records(self):
        return self.env.ref('business_central.action_available_stock_sync_final').read()[0]

    def _ss_get_pending_records(self):
        return self.env.ref('business_central.action_available_stock_sync_pending').read()[0]
    
    def _ss_get_all_records(self):
        return self.env.ref('business_central.action_available_stock_sync').read()[0]

    def _ss_get_processed_records(self):
        return self.env.ref('business_central.action_available_stock_sync_done').read()[0]

    def _ss_get_failed_records(self):
        return self.env.ref('business_central.action_available_stock_sync_failed').read()[0]
    
