# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models,fields

class company(models.Model):
    _inherit = 'res.company'

    manufacturing_lead = fields.Float('Manufacturing Lead Time', required=True
            help="Security days for each manufacturing operation."),

    _defaults = {
        'manufacturing_lead': lambda *a: 1.0,
    }
