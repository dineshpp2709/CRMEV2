from operator import eq
from requests import auth
from odoo import api, fields, models
from itertools import groupby

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class FixedAssetsSyncLogs(models.Model):
    _name = 'business_central.fixed_assets_logs'
    _description = "Fixed Assets Sync Logs"
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

    def _eqs_get_process_logs(self):
        return self.env.ref("business_central.action_fixed_assets_sync_logs").read()[0]

class FixedAssetsSync(models.Model):
    _inherit = 'maintenance.equipment'

    bc_eqs_state = fields.Selection([('pending','Pending'),('fail','Failed'),('done','Done')], "Component Sync Status",default='pending')
    
    def _eqs_run_process(self, debug_mode = False):
        equipments = self.sudo().search([('bc_eqs_state','in',['pending','fail'])])
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            url = '%s/fixedassets'%(base_url)	
            data_transform = (lambda x: {
                "no": x.name or "",
                "description": x.note and x.note[0:100] or "",
                "description2": "",
                "faClassCode": x.category_id and x.category_id.snet_maintenance_code[0:20] or "",
                "faSubclassCode": x.category_id and x.category_id.parent_id and x.category_id.parent_id.snet_maintenance_code[0:20] or "",
                "faLocationCode": x.snet_location and x.snet_location.code[0:20] or '',
                "serialNo": x.serial_no or '',
                "responsibleEmployee": x.employee_id and x.employee_id.barcode or '',
                "installDate": x.effective_date and x.effective_date.strftime("%Y-%m-%d") or "0001-01-01",
                "vendorNo": x.partner_id and x.partner_id.snet_vendor_code[0:20] or "",
                "maintenanceVendorNo": x.snet_maintenance_vendor and x.snet_maintenance_vendor.snet_vendor_code[0:20] or "",
                "underMaintenance": False,
                "amcStartDate": x.effective_date and x.effective_date.strftime("%Y-%m-%d") or "0001-01-01",
                "amcEndDate": x.warranty_date and x.warranty_date.strftime("%Y-%m-%d") or "0001-01-01"
            })
            for equipement in equipments:
                json_request = data_transform(equipement)
                try:
                    response = requests.post(url, data=json.dumps(json_request), auth=token, headers=headers)
                    if response and response.ok:
                        equipement.bc_eqs_state = 'done'
                    else:
                        raise Exception(response.text)
                except Exception as e:
                    equipement.bc_eqs_state = 'fail'
                    self.env['business_central.fixed_assets_logs']._log_error('Error while Syncing Record', str(e),  equipement.name, debug_mode and '%s\n%s'%(url,str(json.dumps(json_request))) or '', debug_mode)
        except Exception as e:        
            self.env['business_central.fixed_assets_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
                        
    def _cron_equipment_sync(self):
        self._eqs_run_process()

    def _eqs_pending_records(self):
        return self.search_count([('bc_eqs_state','in',['pending'])])

    def _eqs_failed_records(self):
        return self.search_count([('bc_eqs_state','in',['fail'])])
    
    def _eqs_done_records(self):
        return self.search_count([('bc_eqs_state','in',['done'])])
    
    def _eqs_total_records(self):
        return self.search_count([])
    
    def _eqs_get_final_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync_final').read()[0]

    def _eqs_get_pending_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync_pending').read()[0]
    
    def _eqs_get_all_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync').read()[0]

    def _eqs_get_processed_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync_done').read()[0]

    def _eqs_get_failed_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync_failed').read()[0]
