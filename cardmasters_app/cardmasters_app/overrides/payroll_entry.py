import frappe
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

class CustomPayrollEntry(PayrollEntry):
    
    def get_advance_deduction(self, component_type: str, item: dict) -> str | None:
        """Hijacked: Identifies custom separation check in Additional Salary"""
        if component_type == "deductions" and item.additional_salary:
            res = frappe.db.get_value(
                "Additional Salary",
                item.additional_salary,
                ["ref_doctype", "ref_docname", "custom_individual_entry"],
                as_dict=True
            )

            if res:
                if res.ref_doctype == "Employee Advance":
                    return res.ref_docname
                
                if res.custom_individual_entry:
                    # Keep the CUSTOM prefix to tell the next method this is our hijack
                    return f"CUSTOM:{item.additional_salary}"
        return None

    def add_advance_deduction_entry(self, item, amount, cost_center, ref_name):
        """Hijacked: Prevents Reference Type error while keeping entries separate"""
        is_custom = ref_name.startswith("CUSTOM:")
        
        # FIX: Journal Entry doesn't allow "Additional Salary" as a reference type.
        # We set them to None for our custom path. 
        # They will STILL be separate lines because they are in this list.
        if is_custom:
            final_ref_name = None
            final_ref_type = None
        else:
            final_ref_name = ref_name
            final_ref_type = "Employee Advance"

        self._advance_deduction_entries.append(
            {
                "employee": item.employee,
                "account": self.get_salary_component_account(item.salary_component),
                "amount": amount,
                "cost_center": cost_center,
                "reference_type": final_ref_type,
                "reference_name": final_ref_name,
            }
        )

    def set_accounting_entries_for_advance_deductions(self, accounts, currencies, company_currency, accounting_dimensions, precision, payable_amount):
        """Identical loop, but now entry.get('reference_type') might be None"""
        for entry in self._advance_deduction_entries:
            # Passing party=employee ensures the "Party" column in the JE is filled 
            payable_amount = self.get_accounting_entries_and_payable_amount(
                entry.get("account"),
                entry.get("cost_center"),
                entry.get("amount"),
                currencies,
                company_currency,
                payable_amount,
                accounting_dimensions,
                precision,
                entry_type="credit",
                accounts=accounts,
                party=entry.get("employee"), 
                reference_type=entry.get("reference_type"),
                reference_name=entry.get("reference_name"),
                is_advance="Yes", 
            )
        return payable_amount