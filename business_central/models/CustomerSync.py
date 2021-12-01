# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

Types = {
    "regular": 'Registered',
    "unregistered": 'Unregistered',
    "overseas": 'Export',
    "deemed_export": 'Deemed Export',
    "consumer": 'Exempted',
    "special_economic_zone": 'SEZ Development',
}


class CustomerSyncLogs(models.Model):
    _name = 'business_central.customer_logs'
    _description = "Customer Sync Logs"
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
    
    
    def _cs_get_process_logs(self):
        return self.env.ref("business_central.action_customer_sync_logs").read()[0]

class CustomerSync(models.Model):
    
    _inherit = 'res.partner'

    bc_cs_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_cs_system_id = fields.Char("Customer System Id")

    def write(self, vals):
        integration_fields = set(['bc_sp_state','bc_sp_system_id','bc_cs_state','bc_cs_system_id','bc_ls_state','bc_ls_system_id','bc_sha_state','bc_sha_customer_address_id','bc_vas_state','bc_vas_vendor_address_id','bc_vs_state','bc_vs_system_id'])
        if not set(vals.keys()).issubset(integration_fields):
            vals['bc_cs_state'] = vals.get('bc_cs_state','pending')
        return super(CustomerSync, self).write(vals)

    def _cs_run_process(self, debug_mode=False):
        contacts = self.sudo().search([('parent_id','=',False),('type','=','contact'),('snet_customer_code','!=',False),('bc_cs_state','in',['pending','fail'])])
        try:
            data_transfor = (lambda x: {
                "CustomerCode" : x.snet_customer_code[0:20],
                "CustName" : x.name and x.name[0:100] or '',
                "CustName2" : x.name and x.name[100:150] or '',
                "Address" : x.street and x.street[0:100] or '',
                "Address2" : x.street2 and x.street2[0:100] or '',
                "PostCode" : x.zip and x.zip[0:20] or '',
                "City" : x.city and x.city[0:30] or '',
                "StateCode" : x.state_id and x.state_id.code[0:10] or '',
                "CountryCode" : x.country_id and x.country_id.code[0:10] or '',
                "ContactPerson" : x.child_ids.filtered(lambda q: q.type == 'contact' and q.snet_customer_code != False) and x.child_ids.filtered(lambda q: q.type == 'contact'and q.snet_customer_code != False)[0].snet_customer_code or '',
                "PhoneNo" : x.phone and x.phone[0:50] or '',
                "MobileNo" : x.mobile and x.mobile[0:50] or '',
                "CurrencyCode" : x.property_product_pricelist and x.property_product_pricelist.currency_id.name[0:10] or '',
                "PaymentTerms" : x.property_payment_term_id and x.property_payment_term_id.snet_payment_term_code[0:10] or '',
                "SalespersonCode" : x.user_id and x.user_id.snet_salesperson_code[0:20] or '',
                "GenBusPostingGroup" : x.snet_gen_bus_posting and x.snet_gen_bus_posting.code[0:20] or '',
                "CustPostGrp" : x.snet_customer_posting and x.snet_customer_posting.code[0:20] or '',
                "Email" : x.email and x.email[0:80] or '',
                "PANNo" : x.snet_pan and x.snet_pan[0:10] or '',
                "TANNo" : x.snet_tan and x.snet_tan[0:10] or '',
                "GSTCustomerType" : Types.get(x.l10n_in_gst_treatment, '0') or '0',
                "GSTRegistrationNo" : x.vat and x.vat[0:15] or '',
                "TDSAssesseeCode" : x.snet_tds_assessee and x.snet_tds_assessee.code[0:10] or '',
                "AssociatedEnterprise" : x.snet_associated_enterprise,
                "FinRegion" : x.snet_fin_region and x.snet_fin_region.code[0:20] or '',
                "FinCostCentre" : x.snet_fin_cost_center and x.snet_fin_cost_center.code[0:20] or '',
                "FinPractice" : x.snet_fin_practice and x.snet_fin_practice.code[0:20] or '',
                "FinBusiness" : x.snet_fin_business and x.snet_fin_business.code[0:20] or '',
                "FinBranch" : x.snet_fin_branch and x.snet_fin_branch.code[0:20] or '',
                "FinZone" : x.snet_fin_zone and x.snet_fin_zone.code[0:20] or '',
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
                    url = '%s/customer'%(base_url)
                    contact = record.pop('contact')
                    headers.pop('If-Match', False)
                    if contact.bc_cs_system_id:
                        url = "%s(CustomerCode='%s')"%(url, record['CustomerCode'])
                        headers['If-Match'] = '*'
                        record.pop('CustomerCode',False)
                        response = requests.patch(url, data=json.dumps(record), auth=token, headers=headers)
                    else:    
                        response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        contact.bc_cs_system_id = data['SystemId']
                        contact.bc_cs_state = 'done'
                    else:
                        contact.bc_cs_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.customer_logs']._log_error('Error while Syncing Record', str(e), contact.snet_customer_code, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        
        except Exception as e:
            contacts.write({'bc_cs_state': 'fail'})
            self.env['business_central.customer_logs']._log_error('Error while Syncing Records', str(e), ','.join(contacts.mapped('snet_customer_code')), debug_mode and traceback.format_exc() or '', debug_mode)
    
    def _cron_customer_sync(self):
        self._cs_run_process()

    def _cs_pending_records(self):
        return self.search_count([('parent_id','=',False),('type','=','contact'),('bc_cs_state','in',['pending']),('snet_customer_code','!=',False)])

    def _cs_failed_records(self):
        return self.search_count([('parent_id','=',False),('type','=','contact'),('bc_cs_state','in',['fail']),('snet_customer_code','!=',False)])
    
    def _cs_done_records(self):
        return self.search_count([('parent_id','=',False),('type','=','contact'),('bc_cs_state','in',['done']),('snet_customer_code','!=',False)])
    
    def _cs_total_records(self):
        return self.search_count([('parent_id','=',False),('type','=','contact'),('snet_customer_code','!=',False)])
    
    def _cs_get_final_records(self):
        return self.env.ref('business_central.action_customer_sync_final').read()[0]

    def _cs_get_pending_records(self):
        return self.env.ref('business_central.action_customer_sync_pending').read()[0]
    
    def _cs_get_all_records(self):
        return self.env.ref('business_central.action_customer_sync').read()[0]

    def _cs_get_processed_records(self):
        return self.env.ref('business_central.action_customer_sync_done').read()[0]

    def _cs_get_failed_records(self):
        return self.env.ref('business_central.action_customer_sync_failed').read()[0]
    
