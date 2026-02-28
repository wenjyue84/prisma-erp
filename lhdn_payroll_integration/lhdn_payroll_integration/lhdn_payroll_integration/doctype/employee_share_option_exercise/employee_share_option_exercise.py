"""Employee Share Option Exercise — DocType controller.

US-084: ESOS/Share Option Gain Calculation and EA Form B10.

ITA 1967 Section 25 and Public Ruling No. 1/2021: gains from ESOS/ESPP
exercise are taxable employment income in the year of exercise.

Taxable Gain = (Market Price on exercise date - Exercise Price) × Shares Exercised

The gain is:
  - Included in annual income for PCB computation in the exercise month
    (treated as an irregular / bonus payment using the LHDN annualisation rule)
  - Disclosed in EA Form Section B10 (ESOS Gain)
"""
import frappe
from frappe.model.document import Document


class EmployeeShareOptionExercise(Document):
    def validate(self):
        self._calculate_taxable_gain()

    def _calculate_taxable_gain(self):
        """Auto-calculate taxable_gain from price spread × shares exercised."""
        market_price = float(self.market_price_on_exercise or 0)
        exercise_price = float(self.exercise_price or 0)
        shares = int(self.shares_exercised or 0)
        gain = (market_price - exercise_price) * shares
        self.taxable_gain = round(max(gain, 0.0), 2)
