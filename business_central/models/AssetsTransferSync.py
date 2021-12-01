from operator import eq
from requests import auth
from requests.api import patch, request
from odoo import api, fields, models
from itertools import groupby

import requests
from requests.auth import HTTPBasicAuth
import json
import traceback

class FixedAssetsSyncLogs(models.Model):
    _name = 'business_central.fixed_transfer_assets_logs'
    _description = "Fixed Assets Transfer Sync Logs"
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

    def _ats_get_process_logs(self):
        return self.env.ref("business_central.action_assets_transfer_logs").read()[0]

class FixedAssetsSync(models.Model):
    _inherit = 'maintenance.equipment'

    def _ats_run_process(self, debug_mode = False):
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('bc.base_url')
            username = self.env['ir.config_parameter'].sudo().get_param('bc.username')
            password = self.env['ir.config_parameter'].sudo().get_param('bc.password')

            token = HTTPBasicAuth(username, password)
            headers = {'Content-Type': 'application/json'}
            
            url = "%s/fixedassets?$filter=('SyncPending' eq 'true')"%(base_url)
            
            response = requests.get(url, auth=token, headers=headers)
            if response and response.ok:
                employee_model = self.env['hr.employee'].sudo()
                location_model = self.env['school_net.asset_locations'].sudo()
                vals = response.json()
                
                for val in vals.get('value',[]):
                    try:
                        sync = False
                        equipement = self.sudo().search([('name','=',val.get('no',''))],limit=1)
                        employee = employee_model.search([('badge','=', val.get('responsibleEmployee',''))], limit=1)
                        location = location_model.search([('code','=', val.get('faLocationCode',''))])
                        
                        if equipement:
                            equipement.snet_disposed = val.get('disposed',False)
                            
                            if location:
                                equipement.location = location
                                sync = True
                            else:
                                sync = False
                                raise Exception("Location '%s' not found in system."%(val.get('faLocationCode','')))

                            if employee:
                                equipement.employee_id = employee
                            else:
                                sync = False
                                raise Exception("Employee '%s' not found in system."%(val.get('responsibleEmployee','')))
                            
                            if sync:
                                patch_url = "%s/fixedassets(no='%s')"%(base_url, val.get('no',''))
                                patch_response = request.patch(patch_url, data=json.dumps({"SyncPending": "false"}), auth=token, headers=headers)
                                if patch_response and patch_response.ok:
                                    # Do nothing. This is done this was coz other way is very complicated. 
                                    # You need to check if response was there and error occured.
                                    # Or was response even came and all.
                                    pass
                                else:
                                    raise Exception("Error while updating sync status for equipment '%s': %s"%(val.get('no',''), patch_response.text))
                            
                            
                        else:
                            raise Exception("Equipment '%s' not found in system."%(val.get('no','')))
                    except Exception as e:
                        self.env['business_central.fixed_transfer_assets_logs']._log_error('Error while Syncing Record', str(e),  val.get('no',''), debug_mode and '%s\n%s'%(url,str(json.dumps(val))) or '', debug_mode)
            else:
                raise Exception(response.text)
        except Exception as e:        
            self.env['business_central.fixed_transfer_assets_logs']._log_error('Error while Syncing Records', str(e), 'error', debug_mode and traceback.format_exc() or '', debug_mode)
                        
    def _cron_assets_transfer_sync(self):
        self._ats_run_process()

    def _ats_total_records(self):
        return self.search_count([])
    
    def _ats_get_all_records(self):
        return self.env.ref('business_central.action_fixed_assets_sync').read()[0]

    