# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class LocationSyncLogs(models.Model):
    _name = 'business_central.location_logs'
    _description = "Location Sync Logs"
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

    def _ls_get_process_logs(self):
        return self.env.ref("business_central.action_location_sync_logs").read()[0]

class LocationSync(models.Model):
    
    _inherit = 'res.partner'

    bc_ls_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_ls_system_id = fields.Char("Location System Id")

    def write(self, vals):
        integration_fields = set(['bc_sp_state','bc_sp_system_id','bc_cs_state','bc_cs_system_id','bc_ls_state','bc_ls_system_id','bc_sha_state','bc_sha_customer_address_id','bc_vas_state','bc_vas_vendor_address_id','bc_vs_state','bc_vs_system_id'])
        if not set(vals.keys()).issubset(integration_fields):
            vals['bc_ls_state'] = vals.get('bc_ls_state','pending')
        return super(LocationSync, self).write(vals)

    def _ls_run_process(self, debug_mode = False):
        contacts = self.sudo().search([('type','=','contact'),('snet_location','=',True),('bc_ls_state','in',['pending','fail'])])
        try:
            data_transfor = (lambda x: {
                "LocationCode" : x.snet_location_code[0:20],
                "LocationName" : x.name and x.name[0:100] or '',
                "LocationName2" : x.name and x.name[100:150] or '',
                "Address" : x.street and x.street[0:100] or '',
                "Address2" : x.street2 and x.street2[0:100] or '',
                "PostCode" : x.zip and x.zip[0:20] or '',
                "City" : x.city and x.city[0:30] or '',
                "StateCode" : x.state_id and x.state_id.code[0:10] or '',
                "CountryCode" : x.country_id and x.country_id.code[0:10] or '',
                "ContactPerson" : x.child_ids.filtered(lambda q: q.type == 'contact' and q.snet_customer_code != False) and x.child_ids.filtered(lambda q: q.type == 'contact'and q.snet_customer_code != False)[0].snet_customer_code or '',
                "PhoneNo" : x.phone and x.phone[0:50] or '',
                "MobileNo" : x.mobile and x.mobile[0:50] or '',
                "GSTRegistrationNo" : x.vat and x.vat[0:15] or '',
                "contact": x
            })
            
            transformed_data = [data_transfor(x) for x in contacts]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
                    
            for record in transformed_data:
                try:
                    url = '%s/location'%(base_url)
                    contact = record.pop('contact')
                    headers.pop('If-Match', False)
                    
                    if contact.bc_ls_system_id:
                        url = "%s(LocationCode='%s')"%(url, record['LocationCode'])
                        headers['If-Match'] = '*'
                        record.pop('LocationCode',False)
                        response = requests.patch(url, data=json.dumps(record), auth=token, headers=headers)
                    else:    
                        response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        contact.bc_ls_system_id = data['SystemId']
                        contact.bc_ls_state = 'done'
                    else:
                        contact.bc_ls_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.location_logs']._log_error('Error while Syncing Record', str(e), contact.snet_location_code, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            contacts.write({'bc_ls_state': 'fail'})
            self.env['business_central.location_logs']._log_error('Error while Syncing Records', str(e), ','.join(contacts.mapped('snet_location_code')), debug_mode and traceback.format_exc() or '', debug_mode)
    
    def _cron_location_sync(self):
        self._ls_run_process()

    def _ls_pending_records(self):
        return self.search_count([('type','=','contact'),('bc_ls_state','in',['pending']),('snet_location','=',True)])

    def _ls_failed_records(self):
        return self.search_count([('type','=','contact'),('bc_ls_state','in',['fail']),('snet_location','=',True)])
    
    def _ls_done_records(self):
        return self.search_count([('type','=','contact'),('bc_ls_state','in',['done']),('snet_location','=',True)])
    
    def _ls_total_records(self):
        return self.search_count([('type','=','contact'),('snet_location','=',True)])
    
    def _ls_get_final_records(self):
        return self.env.ref('business_central.action_location_sync_final').read()[0]

    def _ls_get_pending_records(self):
        return self.env.ref('business_central.action_location_sync_pending').read()[0]
    
    def _ls_get_all_records(self):
        return self.env.ref('business_central.action_location_sync').read()[0]

    def _ls_get_processed_records(self):
        return self.env.ref('business_central.action_location_sync_done').read()[0]

    def _ls_get_failed_records(self):
        return self.env.ref('business_central.action_location_sync_failed').read()[0]
    
