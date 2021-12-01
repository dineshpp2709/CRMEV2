from typing import Sequence
from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback


class TermsConditionsSyncLogs(models.Model):
    _name = 'business_central.purchase_terms_logs'
    _description = "Purchase Order T&C Sync Logs"
    _order = 'id desc'
    
    name = fields.Char("Message")
    message = fields.Char("Description")
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

    def _tnc_get_process_logs(self):
        return self.env.ref("business_central.action_terms_conditions_sync_logs").read()[0]

class TermsConditionSync(models.Model):
    _inherit = 'school_net.purchase_terms'

    bc_tnc_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_tnc_system_id = fields.Char("PO System Id")

    def _tnc_run_process(self, debug_mode = False):
        orders = self.sudo().search([('snet_purchase_id','!=',False),('bc_tnc_state','in',['pending','fail'])])
        try:
            data_transfor = (lambda line, lines: {
                "DocType": "Order",
                "DocNo": line.snet_purchase_id.name[0:20],
                "LineNo": 30000 + lines.index(line.id) + 1,
                "SequenceNo": str(lines.index(line.id) + 1),
                "Heading": line.snet_name or '',
                "Description": line.snet_description or '',
                "Bold": line.snet_bold,
                "UnderLine": line.snet_underline,
                "order": line
            })

            transformed_data = [data_transfor(x,list(x.snet_purchase_id.mapped('snet_terms.id'))) for x in orders]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            url = '%s/purchtcs'%(base_url)
            token = HTTPBasicAuth(username, password)
            for record in transformed_data:
                try:
                    order = record.pop('order')
                    
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        order.bc_tnc_system_id = data['SystemId']
                        order.bc_tnc_state = 'done'
                    else:
                        order.bc_tnc_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.purchase_terms_logs']._log_error('Error while Syncing Record', str(e), '%s - %s'%(order.snet_purchase_id.name,order.snet_name), debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            orders.write({'bc_tnc_state': 'fail'})
            self.env['business_central.purchase_terms_logs']._log_error('Error while Syncing Records', str(e), ','.join(orders.mapped('snet_purchase_id.name')), debug_mode and traceback.format_exc() or '', debug_mode)

    def _cron_terms_conditions_sync(self):
        self._tnc_run_process()

    def _tnc_pending_records(self):
        return self.search_count([('snet_purchase_id','!=',False),('bc_tnc_state','in',['pending'])])

    def _tnc_failed_records(self):
        return self.search_count([('snet_purchase_id','!=',False),('bc_tnc_state','in',['fail'])])
    
    def _tnc_done_records(self):
        return self.search_count([('snet_purchase_id','!=',False),('bc_tnc_state','in',['done'])])
    
    def _tnc_total_records(self):
        return self.search_count([('snet_purchase_id','!=',False),])
    
    def _tnc_get_final_records(self):
        return self.env.ref('business_central.action_terms_conditions_sync_final').read()[0]

    def _tnc_get_pending_records(self):
        return self.env.ref('business_central.action_terms_conditions_sync_pending').read()[0]
    
    def _tnc_get_all_records(self):
        return self.env.ref('business_central.action_terms_conditions_sync').read()[0]

    def _tnc_get_processed_records(self):
        return self.env.ref('business_central.action_terms_conditions_sync_done').read()[0]

    def _tnc_get_failed_records(self):
        return self.env.ref('business_central.action_terms_conditions_sync_failed').read()[0]
