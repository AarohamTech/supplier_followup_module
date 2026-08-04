"""The reply-table parser must never turn forwarded email headers or
signatures into material rows.

Prod case: an internal forward ("Fw: Still Rate Not Received") rendered a
SUPPLIER REPLY TABLE whose rows were the forwarded To:/Cc: recipient lists —
loose mode treated any line with 3+ semicolon-separated cells as a material
row, and the primary-section trim only cut at a line that was exactly
"From:" (real forwarded headers are "From: Amol Patil <...>")."""
from __future__ import annotations

import unittest

from app.services.reply_table_parser import parse_reply_table


FORWARDED_MAIL = """We will debit days x 10 rs per mdn if rates not given today
 All team
Get Outlook for Android<https://aka.ms/AAb9ysg>
________________________________
From: Amol Patil <amol.patil@zanvargroup.com>
Sent: Tuesday, August 4, 2026 11:23:00 am
To: sales@hariomtech.in <sales@hariomtech.in>; Harshal <sourcing@hariomtech.in>; Sandeep Pawar <sandeep@hariomtech.in>; Sales2 <sales2@hariomtech.in>
Cc: Bhagwanpatil <bhagwanpatil@zanvargroup.com>; kfplu1.mshopmaint <kfplu1.mshopmaint@zanvargroup.com>
Subject: RE: Still Rate Not Received

Dear All,

Still rate not received, please give us rate immediately.

MATERIAL DESCRIPTION
QTY
MDN NO
MDN DATE
resp. person
FILTER ELEMENT P-G-UL-12A-50UW-SZ TAISEI KOGYO CO LTD
2
4436
29.07.2026
KAPIL
"""


class ForwardedMailTests(unittest.TestCase):
    def test_forwarded_chain_produces_no_rows(self):
        self.assertEqual(parse_reply_table(FORWARDED_MAIL), [])

    def test_recipient_list_lines_are_never_rows(self):
        body = (
            "To: sales@hariomtech.in <sales@hariomtech.in>; Harshal <sourcing@hariomtech.in>; Sales2 <sales2@hariomtech.in>\n"
            "Cc: a@zanvargroup.com; b@zanvargroup.com; c@zanvargroup.com\n"
        )
        self.assertEqual(parse_reply_table(body), [])

    def test_signature_lines_without_data_are_not_rows(self):
        body = "Amol A. Patil; Store Incharge; Kolhapur Works\n"
        self.assertEqual(parse_reply_table(body), [])

    def test_mailto_style_forward_with_name_only_cc_produces_no_rows(self):
        # Second prod case: "[mailto:...]" headers and a Cc: of bare NAMES
        # (no email addresses) — rendered "Cc: Sanjay Jadhav | Ashok Sonale"
        # as a material row on the old parser.
        body = (
            "From: ED Development [mailto:ed.development@zanvargroup.com]\n"
            "Sent: 31 July 2026 02:37 PM\n"
            "To: Edsteel Purchase\n"
            "Cc: Sanjay Jadhav; Ashok Sonale; Pradip Patil\n"
            "Subject: Arrange conveyor roller .\n\n"
            "Please arrange conveyor roller ASPR Drawing  .....20 nos\n\n"
            "Mob. 965 714 9007\n"
            "Pradeep B PatiL; Development; Zanvar Group\n"
            "Hariom Enterprises; Hariomtech; Kolhapur\n"
        )
        self.assertEqual(parse_reply_table(body), [])


class LegitTableTests(unittest.TestCase):
    def test_markdown_table_still_parses(self):
        body = (
            "| CRM No | Material Name | Qty | Commitment Date | Status |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 2627-003726 | HOLDER-TCLNL 2525 M-12 | 2 | 15-08-2026 | Confirmed |\n"
        )
        rows = parse_reply_table(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["material_code"], "2627-003726")
        self.assertEqual(rows[0]["quantity"], 2.0)
        self.assertEqual(rows[0]["supplier_status"], "CONFIRMED")

    def test_loose_pipe_row_with_quantity_still_parses(self):
        body = "2627-003726 | HOLDER-TCLNL 2525 M-12 | 2 | 15-08-2026\n"
        rows = parse_reply_table(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 2.0)

    def test_reply_above_quoted_chain_still_parses(self):
        body = (
            "| CRM No | Material | Qty | Date | Status |\n"
            "| 2627-000001 | WIDGET | 5 | 20-08-2026 | Confirmed |\n"
            "\n"
            "From: Procurement <stores@hariomtech.in>\n"
            "To: sales@vendor.com <sales@vendor.com>; second@vendor.com; third@vendor.com\n"
        )
        rows = parse_reply_table(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["material_code"], "2627-000001")


if __name__ == "__main__":
    unittest.main()
