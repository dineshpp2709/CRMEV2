from requests import auth
from odoo import api, fields, models

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

GSTTypes = {
	"regular": 'Registered',
	"unregistered": 'Unregistered',
	"overseas": 'Export',
	"deemed_export": 'Deemed Export',
	"consumer": 'Exempted',
	"special_economic_zone": 'SEZ Development',
}

class InvoiceSyncLogs(models.Model):
	_name = 'business_central.invoice_logs'
	_description = "Invoice Sync Logs"
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

	def _ios_get_process_logs(self):
		return self.env.ref("business_central.action_invoice_sync_logs").read()[0]

class InvoiceSync(models.Model):
	_inherit = 'account.move'

	bc_ios_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], default='pending')
	bc_ios_system_id = fields.Char("Invoice System Id")

	def _ios_run_process(self, debug_mode = False):
		orders = self.sudo().search([('state','in',['posted']),('move_type', '=', 'in_invoice'),('bc_ios_state','in',['pending','fail'])])
		try:
			line_transfor = (lambda line, x: {
				"DocType": 'Invoice',
				"DocNo": x.move_id.name and x.move_id.name[0:20] or '',
				"LineNo": line,
				"LineType": 'Item',
				"ItemNo": x.product_id and x.product_id.snet_item_code[0:10] or '',
				"Description" : x.product_id and x.product_id.name and x.product_id.name[0:100] or '',
				"Quantity" : x.quantity,
				"UOM": x.product_uom_id and x.product_uom_id.snet_uom_code[0:10] or '',
				"UnitCost" : x.price_unit
			})

			data_transfor = (lambda x: {
				"DocumentType" : 'Invoice',
				"OrderNo" : x.name and x.name[0:20] or '',
				"VendorNo" : x.partner_id.snet_vendor_code and x.partner_id.snet_vendor_code[0:20] or '',
				"OrderDate" : x.invoice_date and x.invoice_date.strftime("%Y-%m-%d"),
				"LocationCode" : x.snet_location_id and x.snet_location_id.code[0:10] or '',
				"Purchaser" : x.invoice_user_id and x.invoice_user_id.snet_salesperson_code[0:20] or '',
				"PaymentTerms" : x.invoice_payment_term_id and x.invoice_payment_term_id.snet_payment_term_code[0:10] or '',
				"QuoteNo" : x.invoice_origin and (list(x.invoice_origin.split(','))[0])[0:20] or '',
				"CurrencyCode" : x.currency_id and x.currency_id.name[0:10] or '',
				"NoOfLines" : x.invoice_line_ids and len(x.invoice_line_ids) or 0,
				"LineAmountTotal" : x.amount_total,
				"FinRegion" : x.snet_fin_region and x.snet_fin_region.code[0:20] or '',
				"FinCostCentre" : x.snet_fin_cost_center and x.snet_fin_cost_center.code[0:20] or '',
				"FinPractice" : x.snet_fin_practice and x.snet_fin_practice.code[0:20] or '',
				"FinBusiness" : x.snet_fin_business and x.snet_fin_business.code[0:20] or '',
				"FinBranch" : x.snet_fin_branch and x.snet_fin_branch.code[0:20] or '',
				"FinZone" : x.snet_fin_zone and x.snet_fin_zone.code[0:20] or '',
				"purchlines": [line_transfor(lineno, line) for lineno, line in enumerate(x.invoice_line_ids,1000)],
				"order": x
			})
			
			transformed_data = [data_transfor(x) for x in orders]
			# raise Exception(transformed_data)

			base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
			username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
			password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

			url = '%s/purchaseorders'%(base_url)
			token = HTTPBasicAuth(username, password)
			headers = {'Content-Type': 'application/json'}
					
			for record in transformed_data:
				try:
					order = record.pop('order')
					response = requests.post(url, data=json.dumps(record), auth=token, headers=headers)
					
					if response and response.ok:
						data = response.json()
						order.bc_ios_system_id = data['SystemId']
						order.bc_ios_state = 'done'
					else:
						order.bc_ios_state = 'fail'
						raise Exception(response.text)
				
				except Exception as e:
					self.env['business_central.invoice_logs']._log_error('Error while Syncing Record', str(e), order.name)
		except Exception as e:
			orders.write({'bc_ios_state': 'fail'})
			self.env['business_central.invoice_logs']._log_error('Error while Syncing Records', str(e), ','.join(orders.mapped('name')), debug_mode and traceback.format_exc() or '', debug_mode)

	def _cron_invoice_sync(self):
		self._ios_run_process()

	def _ios_pending_records(self):
		return self.search_count([('state','in',['posted']),('move_type', '=', 'in_invoice'),('bc_ios_state','in',['pending'])])

	def _ios_failed_records(self):
		return self.search_count([('state','in',['posted']),('move_type', '=', 'in_invoice'),('bc_ios_state','in',['fail'])])
	
	def _ios_done_records(self):
		return self.search_count([('state','in',['posted']),('move_type', '=', 'in_invoice'),('bc_ios_state','in',['done'])])
	
	def _ios_total_records(self):
		return self.search_count([('state','in',['posted']),('move_type', '=', 'in_invoice')])
	
	def _ios_get_final_records(self):
		return self.env.ref('business_central.action_invoice_sync_final').read()[0]

	def _ios_get_pending_records(self):
		return self.env.ref('business_central.action_invoice_sync_pending').read()[0]
	
	def _ios_get_all_records(self):
		return self.env.ref('business_central.action_invoice_sync').read()[0]

	def _ios_get_processed_records(self):
		return self.env.ref('business_central.action_invoice_sync_done').read()[0]

	def _ios_get_failed_records(self):
		return self.env.ref('business_central.action_invoice_sync_failed').read()[0]
