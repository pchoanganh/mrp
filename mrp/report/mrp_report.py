# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields,models


class report_workcenter_load(models.Model):
    _name="report.workcenter.load"
    _description="Work Center Load"
    _auto = False
    _log_access = False

    name = fields.Char('Week', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True)
    cycle = fields.Float('Number of Cycles')
    hour = fields.Float('Number of Hours')


    def init(self, cr):
        cr.execute("""
            create or replace view report_workcenter_load as (
                SELECT
                    min(wl.id) as id,
                    to_char(p.date_planned,'YYYY:mm:dd') as name,
                    SUM(wl.hour) AS hour,
                    SUM(wl.cycle) AS cycle,
                    wl.workcenter_id as workcenter_id
                FROM
                    mrp_production_workcenter_line wl
                    LEFT JOIN mrp_production p
                        ON p.id = wl.production_id
                GROUP BY
                    wl.workcenter_id,
                    to_char(p.date_planned,'YYYY:mm:dd')
            )""")



class report_mrp_inout(models.Model):
    _name="report.mrp.inout"
    _description="Stock value variation"
    _auto = False
    _log_access = False
    _rec_name = 'date'

    date = fields.Char('Week', required=True)
    value = fields.Float('Stock value', required=True, digits=(16,2))
    company_id = fields.Many2one('res.company', 'Company', required=True)


    def init(self, cr):
        cr.execute("""
            create or replace view report_mrp_inout as (
                select
                    min(sm.id) as id,
                    to_char(sm.date,'YYYY:IW') as date,
                    sum(case when (sl.usage='internal') then
                        sm.price_unit * sm.product_qty
                    else
                        0.0
                    end - case when (sl2.usage='internal') then
                        sm.price_unit * sm.product_qty
                    else
                        0.0
                    end) as value, 
                    sm.company_id
                from
                    stock_move sm
                left join product_product pp
                    on (pp.id = sm.product_id)
                left join product_template pt
                    on (pt.id = pp.product_tmpl_id)
                left join stock_location sl
                    on ( sl.id = sm.location_id)
                left join stock_location sl2
                    on ( sl2.id = sm.location_dest_id)
                where
                    sm.state = 'done'
                group by
                    to_char(sm.date,'YYYY:IW'), sm.company_id
            )""")
