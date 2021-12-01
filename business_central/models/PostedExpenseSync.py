# -*- coding: utf-8 -*-

from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class PostedExpenseSyncLogs(models.Model):
    _name = 'business_central.posted_expense_logs'
    _description = "Expense Posting Sync Logs"
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
    
    def _eps_get_process_logs(self):
        return self.env.ref("business_central.action_posted_expense_sync_logs").read()[0]

class PostedExpenseSync(models.Model):
    
    _inherit = 'hr.expense.sheet'

    bc_eps_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    
    def _eps_run_process(self, debug_mode = False):
        try:
            orders = self.sudo().search_count([('state','=','approve')])
            pages = int(orders/80)
            
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')
            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            for page in range(0, pages+1):
                orders = self.sudo().search([('state','=','approve')], limit = 80, offset= page*80)
                try:
                    requested_order = ' or '.join(list(map(lambda x: "ExpNo eq '%s'"%(x), orders.mapped('name'))))
                    url = '%s/postedexps?$filter=%s'%(base_url, requested_order)
                    response = requests.get(url, auth=token, headers=headers)
                    if response and response.ok:
                        data = response.json()
                        for res in data['value']:
                            try:
                                expense = orders.filtered(lambda x: x.name == res['ExpNo'])
                                if expense:
                                    expense = expense[0].sudo()
                                    if expense.state == 'approve':
                                        expense.action_sheet_move_create()
                                        expense.snet_posted_on = res['PostingDate']
                                        expense.bc_eps_state = 'done'
                                else:
                                    expense.bc_eps_state = 'fail'
                                    raise Exception("Expense %s received from Business Central, not found in odoo."%(res['ExpNo']))
                            
                            except Exception as e:
                                self.env['business_central.posted_expense_logs']._log_error('Error while posting record', str(e), res['ExpNo'], debug_mode and '%s'%(url) or '', debug_mode)
                    else:
                        raise Exception(response.text)
                except Exception as e:
                    orders.write({'bc_eps_state':'fail'})
                    self.env['business_central.posted_expense_logs']._log_error('Error while Syncing Record', str(e), ', '.join(orders.mapped('name')), debug_mode and '%s'%(url) or '', debug_mode)
        except Exception as e:
            self.env['business_central.posted_expense_logs']._log_error('Error while Syncing Records', str(e), '', debug_mode and traceback.format_exc() or '', debug_mode)
            
                        
            
    def _cron_expense_post_sync(self):
        self._eps_run_process()

    # def _eps_final_records(self):
    #     return self.search_count([('bc_eps_state','in',['pending']),('ref','!=',False)])

    def _eps_pending_records(self):
        return self.search_count([('bc_eps_state','in',['pending']),('state','=','approve')])

    def _eps_failed_records(self):
        return self.search_count([('bc_eps_state','in',['fail']),('state','=','approve')])
    
    def _eps_done_records(self):
        return self.search_count([('bc_eps_state','in',['done'])])
    
    def _eps_total_records(self):
        return self.search_count([('state','=','approve')])
    
    def _eps_get_final_records(self):
        return self.env.ref('business_central.action_posted_expense_sync_final').read()[0]

    def _eps_get_pending_records(self):
        return self.env.ref('business_central.action_posted_expense_sync_pending').read()[0]
    
    def _eps_get_all_records(self):
        return self.env.ref('business_central.action_posted_expense_sync').read()[0]

    def _eps_get_processed_records(self):
        return self.env.ref('business_central.action_posted_expense_sync_done').read()[0]

    def _eps_get_failed_records(self):
        return self.env.ref('business_central.action_posted_expense_sync_failed').read()[0]
    
