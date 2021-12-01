from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class ExpenseSyncLogs(models.Model):
    _name = 'business_central.expense_logs'
    _description = "Expense Sync Logs"
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

    def _exs_get_process_logs(self):
        return self.env.ref("business_central.action_expense_sync_logs").read()[0]

class ExpenseSync(models.Model):
    _inherit = 'hr.expense.sheet'

    bc_exs_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
    bc_exs_system_id = fields.Char("Expense System Id")

    def _exs_run_process(self, debug_mode = False):
        expenses = self.sudo().search([('state','in',['approve']),('bc_exs_state','in',['pending','fail'])])
        try:
            line_transfor = (lambda line, x: {
                "DocNo": x.sheet_id.name and x.sheet_id.name[0:20] or '',
                "LineNo": line,
                "ExpCode": x.product_id and x.product_id.snet_item_code[0:10] or '',
                "Amount": x.total_amount,
                "FinRegion" : x.snet_region and x.snet_region.code[0:20] or '',
                "FinCostCentre" : x.snet_cost_center and x.snet_cost_center.code[0:20] or '',
                "FinPractice" : x.snet_practice and x.snet_practice.code[0:20] or '',
                "FinBusiness" : x.snet_business and x.snet_business.code[0:20] or '',
                "FinBranch" : x.snet_branch and x.snet_branch.code[0:20] or '',
                "FinZone" : x.snet_zone and x.snet_zone.code[0:20] or '',
            })

            data_transfor = (lambda x: {
                "ExpNo": x.name and x.name[0:20] or '',
                "EmployeeNo": x.employee_id and x.employee_id.barcode[0:20] or '',
                "NoOfLines": x.expense_line_ids and len(x.expense_line_ids) or 0,
                "LineAmountTotal": x.total_amount,
                "PostingDate": x.snet_approval_date and x.snet_approval_date.strftime("%Y-%m-%d") or '0001-01-01',
                "explines": [line_transfor(lineno, line) for lineno, line in enumerate(x.expense_line_ids,1000)],
                "expense": x
            })
            
            transformed_data = [data_transfor(x) for x in expenses]

            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            url = '%s/exps?$expand=explines'%(base_url)
            token = HTTPBasicAuth(username, password)
            for record in transformed_data:
                try:
                    expense = record.pop('expense')
                    
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
                    
                    if response and response.ok:
                        data = response.json()
                        expense.bc_exs_system_id = data['SystemId']
                        expense.bc_exs_state = 'done'
                    else:
                        expense.bc_exs_state = 'fail'
                        raise Exception(response.text)
                
                except Exception as e:
                    self.env['business_central.expense_logs']._log_error('Error while Syncing Record', str(e), expense.name, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
        except Exception as e:
            expenses.write({'bc_exs_state': 'fail'})
            self.env['business_central.expense_logs']._log_error('Error while Syncing Records', str(e), ','.join(expenses.mapped('name')), debug_mode and traceback.format_exc() or '', debug_mode)
    def _cron_expense_sync(self):
        self._exs_run_process()

    def _exs_pending_records(self):
        return self.search_count([('state','in',['approve']),('bc_exs_state','in',['pending'])])

    def _exs_failed_records(self):
        return self.search_count([('state','in',['approve']),('bc_exs_state','in',['fail'])])
    
    def _exs_done_records(self):
        return self.search_count([('bc_exs_state','in',['done'])])
    
    def _exs_total_records(self):
        return self.search_count([('state','in',['approve'])])
    
    def _exs_get_final_records(self):
        return self.env.ref('business_central.action_expense_sync_final').read()[0]

    def _exs_get_pending_records(self):
        return self.env.ref('business_central.action_expense_sync_pending').read()[0]
    
    def _exs_get_all_records(self):
        return self.env.ref('business_central.action_expense_sync').read()[0]

    def _exs_get_processed_records(self):
        return self.env.ref('business_central.action_expense_sync_done').read()[0]

    def _exs_get_failed_records(self):
        return self.env.ref('business_central.action_expense_sync_failed').read()[0]