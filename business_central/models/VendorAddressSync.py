# -*- coding: utf-8 -*-

from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class ShippingAddressSyncLogs(models.Model):
    _name = 'business_central.vendor_address_logs'
    _description = "Vendor Addres Sync Logs"
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
    
    def _vas_get_process_logs(self):
        return self.env.ref("business_central.action_vendor_address_sync_logs").read()[0]

class ShippingAddressSync(models.Model):
    
    _inherit = 'res.partner'

    bc_vas_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_vas_vendor_address_id = fields.Char("Vendor Address System Id")
    
    def write(self, vals):
        integration_fields = set(['bc_sp_state','bc_sp_system_id','bc_cs_state','bc_cs_system_id','bc_ls_state','bc_ls_system_id','bc_sha_state','bc_sha_customer_address_id','bc_vas_state','bc_vas_vendor_address_id','bc_vs_state','bc_vs_system_id'])
        if not set(vals.keys()).issubset(integration_fields):
            vals['bc_vas_state'] = vals.get('bc_vas_state','pending')
        return super(ShippingAddressSync, self).write(vals)

    def _vas_run_process(self, debug_mode = False):
        contacts = self.sudo().search([('parent_id.snet_vendor_code','!=',False),('bc_vas_state','in',['pending','fail']),('type','!=','contact')])
        try:
            vendor_transform = (lambda x: {
                "VendorCode" : x.parent_id and x.parent_id.snet_vendor_code[0:20] or '',
                "OrderAddressCode" : x.snet_address_code and x.snet_address_code[0:20] or '',
                "OrderAddressName" : x.parent_id and x.parent_id.name[0:100] or '',
                "OrderAddressName2" : x.parent_id and x.parent_id.name[100:150] or '',
                "Address" : x.street and x.street[0:100] or '',
                "Address2" : x.street2 and x.street2[0:100] or '' ,
                "PostCode" : x.zip and x.zip[0:20] or '',
                "City" : x.city and x.city[0:30] or '',
                "StateCode" : x.state_id and x.state_id.code[0:10] or '',
                "CountryCode" : x.country_id and x.country_id.code[0:10] or '',
                "ContactPerson" : x.name and x.name[0:50] or '',
                "PhoneNo" : x.phone and x.phone[0:50] or '',
                "MobileNo" : x.mobile and x.mobile[0:30] or '',
                "GSTRegistrationNo" : x.l10n_in_shipping_gstin or (x.parent_id and x.parent_id.vat and x.parent_id.vat[0:15] or ''),
                "contact": x
            })
            transformed_data_vendor = [vendor_transform(x) for x in contacts]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')
        
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
                    
            for record in transformed_data_vendor:
                try:
                    url = '%s/ordereaddress'%(base_url)
            
                    contact = record.pop('contact')
                    headers.pop('If-Match', False)
                    
                    if contact.bc_vas_vendor_address_id:
                        url = "%s(VendorCode='%s',OrderAddressCode='%s')"%(url, record['VendorCode'],record['OrderAddressCode'])
                        headers['If-Match'] = '*'
                        record.pop('VendorCode',False)
                        record.pop('OrderAddressCode',False)
                        response = requests.patch(url, data=json.dumps(record), auth=token, headers=headers)
                    else:    
                        response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        contact.bc_vas_vendor_address_id = data['SystemId']
                        contact.bc_vas_state = 'done'
                    else:
                        contact.bc_vas_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.vendor_address_logs']._log_error('Error while Syncing Record', str(e),  (contact.parent_id and contact.parent_id.snet_vendor_code or ''), debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            contacts.write({'bc_vas_state': 'fail'})
            self.env['business_central.vendor_address_logs']._log_error('Error while Syncing Records', str(e), ','.join(contacts.mapped('parent_id.snet_vendor_code')), debug_mode and traceback.format_exc() or '', debug_mode)
    
        
    def _cron_vendor_address_sync(self):
        self._vas_run_process()

    # def _vas_final_records(self):
    #     return self.search_count([('bc_vas_state','in',['pending']),('ref','!=',False)])

    def _vas_pending_records(self):
        return self.search_count([('parent_id.snet_vendor_code','!=',False),('bc_vas_state','in',['pending']),('type','!=','contact')])

    def _vas_failed_records(self):
        return self.search_count([('parent_id.snet_vendor_code','!=',False),('bc_vas_state','in',['fail']),('type','!=','contact')])
    
    def _vas_done_records(self):
        return self.search_count([('parent_id.snet_vendor_code','!=',False),('bc_vas_state','in',['done']),('type','!=','contact')])
    
    def _vas_total_records(self):
        return self.search_count([('parent_id.snet_vendor_code','!=',False),('type','!=','contact')])
    
    def _vas_get_final_records(self):
        return self.env.ref('business_central.action_vendor_address_sync_final').read()[0]

    def _vas_get_pending_records(self):
        return self.env.ref('business_central.action_vendor_address_sync_pending').read()[0]
    
    def _vas_get_all_records(self):
        return self.env.ref('business_central.action_vendor_address_sync').read()[0]

    def _vas_get_processed_records(self):
        return self.env.ref('business_central.action_vendor_address_sync_done').read()[0]

    def _vas_get_failed_records(self):
        return self.env.ref('business_central.action_vendor_address_sync_failed').read()[0]
    
