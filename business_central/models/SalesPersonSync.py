# -*- coding: utf-8 -*-

from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback
import time

class SalesPersonSyncLogs(models.Model):
    _name = 'business_central.salesperson_logs'
    _description = "Sales Person Sync Logs"
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
    
    def _sp_get_process_logs(self):
        return self.env.ref("business_central.action_salesperson_sync_logs").read()[0]

class SalesPersonSync(models.Model):
    
    _inherit = 'res.partner'

    bc_sp_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_sp_system_id = fields.Text("BC Sales Person Id")
    
    def write(self, vals):
        integration_fields = set(['bc_sp_state','bc_sp_system_id','bc_cs_state','bc_cs_system_id','bc_ls_state','bc_ls_system_id','bc_sha_state','bc_sha_customer_address_id','bc_vas_state','bc_vas_vendor_address_id','bc_vs_state','bc_vs_system_id'])
        if not set(vals.keys()).issubset(integration_fields):
            vals['bc_sp_state'] = vals.get('bc_sp_state','pending')
        return super(SalesPersonSync, self).write(vals)

    

    def _sp_run_process(self, debug_mode = False):
        salespersons = self.sudo().search([('snet_salesperson_code', '!=', False),('bc_sp_state','in',['pending','fail'])])
        try:
            transformed_data = [{
                'Code': x.snet_salesperson_code and x.snet_salesperson_code[0:20] or '',
                'Name': x.name and x.name[0:50] or '',
                'contact' : x
            } for x in salespersons]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            for record in transformed_data:
                try:
                    url = '%s/salesperson'%(base_url)
                    
                    contact = record.pop('contact')
                    headers.pop('If-Match', False)
                    
                    if contact.bc_sp_system_id:
                        url = "%s(Code='%s')"%(url, record['Code'])
                        headers['If-Match'] = '*'
                        record.pop('Code',False)
                        response = requests.patch(url, data=json.dumps(record), auth=token, headers=headers)
                    else:    
                        response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        contact.bc_sp_system_id = data['SystemId']
                        contact.bc_sp_state = 'done'
                    else:
                        contact.bc_vas_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.salesperson_logs']._log_error('Error while Syncing Record', str(e),  (contact.snet_salesperson_code or ''), debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            salespersons.write({'bc_sp_state': 'fail'})
            self.env['business_central.salesperson_logs']._log_error('Error while Syncing Records', str(e), ','.join(salespersons.mapped('snet_salesperson_code')), debug_mode and traceback.format_exc() or '', debug_mode)
    
        
    def _cron_salesperson_sync(self):
        self._sp_run_process()

    # def _sp_final_records(self):
    #     return self.search_count([('bc_sp_state','in',['pending']),('ref','!=',False)])

    def _sp_pending_records(self):
        return self.search_count([('bc_sp_state','in',['pending']),('snet_salesperson_code', '!=', False)])

    def _sp_failed_records(self):
        return self.search_count([('bc_sp_state','in',['fail']),('snet_salesperson_code', '!=', False)])
    
    def _sp_done_records(self):
        return self.search_count([('bc_sp_state','in',['done']),('snet_salesperson_code', '!=', False)])
    
    def _sp_total_records(self):
        return self.search_count([('snet_salesperson_code', '!=', False)])
    
    def _sp_get_final_records(self):
        return self.env.ref('business_central.action_salesperson_sync_final').read()[0]

    def _sp_get_pending_records(self):
        return self.env.ref('business_central.action_salesperson_sync_pending').read()[0]
    
    def _sp_get_all_records(self):
        return self.env.ref('business_central.action_salesperson_sync').read()[0]

    def _sp_get_processed_records(self):
        return self.env.ref('business_central.action_salesperson_sync_done').read()[0]

    def _sp_get_failed_records(self):
        return self.env.ref('business_central.action_salesperson_sync_failed').read()[0]
    
