from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class BomSyncLogs(models.Model):
    _name = 'business_central.bom_logs'
    _description = "Bom Sync Logs"
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

    def _bs_get_process_logs(self):
        return self.env.ref("business_central.action_bom_sync_logs").read()[0]

class BomSync(models.Model):
	_inherit = 'mrp.bom'

	bc_bs_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
	bc_bs_system_id = fields.Char("Bom System Id")

	def write(self, vals):
		vals['bc_bs_state'] = vals.get('bc_bs_state','pending')
		return super(BomSync, self).write(vals)

	def _bs_run_process(self, debug_mode = False):
		boms = self.sudo().search([('bc_bs_state','in',['pending','fail'])])
		try:
			line_transfor = (lambda line, x: {
				"parentItemNo" : x.product_id and x.parent_product_tmpl_id and x.parent_product_tmpl_id.snet_item_code[0:10] or '',
				"lineNo": line,
				"type" : 'Item',
				"no" : x.product_id and x.product_id.snet_item_code[0:10] or '',
				"unitOfMeasureCode" : x.product_uom_id and x.product_uom_id.snet_uom_code[0:10] or '',
				"quantityPer" : x.product_qty
			})

			data_transfor = (lambda x: {
				"No": x.product_tmpl_id and x.product_tmpl_id.snet_item_code and x.product_tmpl_id.snet_item_code[0:10] or '',
				"NoofLines": x.bom_line_ids and len(x.bom_line_ids) or 0,
				"comps": [line_transfor(lineno, line) for lineno, line in enumerate(x.bom_line_ids,1000)],
				"order": x
			})

			transformed_data = [data_transfor(x) for x in boms]
			base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
			username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
			password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

			token = HTTPBasicAuth(username, password)
			headers = {'Content-Type': 'application/json'}
					
			for record in transformed_data:
				try:
					url = '%s/ItemBOMs?$expand=comps'%(base_url)
					bom = record.pop('order')
					headers.pop('If-Match', False)  
					response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
					
					if response and response.ok:
						data = response.json()
						bom.bc_bs_system_id = data['SystemId']
						bom.bc_bs_state = 'done'
					else:
						bom.bc_bs_state = 'fail'
						raise Exception(response.text)
				
				except Exception as e:
					self.env['business_central.bom_logs']._log_error('Error while Syncing Record', str(e), bom.id, debug_mode and '%s\n%s'%(url,str(json.dumps(record))) or '', debug_mode)
		except Exception as e:
			boms.write({'bc_bs_state': 'fail'})
			self.env['business_central.bom_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)

	def _cron_bom_sync(self):
		self._bs_run_process()

	def _bs_pending_records(self):
		return self.search_count([('bc_bs_state','in',['pending'])])

	def _bs_failed_records(self):
		return self.search_count([('bc_bs_state','in',['fail'])])
	
	def _bs_done_records(self):
		return self.search_count([('bc_bs_state','in',['done'])])
	
	def _bs_total_records(self):
		return self.search_count([])
	
	def _bs_get_final_records(self):
		return self.env.ref('business_central.action_bom_sync_final').read()[0]

	def _bs_get_pending_records(self):
		return self.env.ref('business_central.action_bom_sync_pending').read()[0]
	
	def _bs_get_all_records(self):
		return self.env.ref('business_central.action_bom_sync').read()[0]

	def _bs_get_processed_records(self):
		return self.env.ref('business_central.action_bom_sync_done').read()[0]

	def _bs_get_failed_records(self):
		return self.env.ref('business_central.action_bom_sync_failed').read()[0]
