// Mirrors form8825/schema.py's LINE_ITEM_MAP — kept in sync manually since
// the two live in different languages with no shared schema tooling here.
export const INCOME_LABELS: Record<string, string> = {
  gross_rents: "2a  Gross rents",
  other_income: "2b  Other income",
}

export const EXPENSE_LABELS: Record<string, string> = {
  advertising: "3  Advertising",
  auto_travel: "4  Auto and travel",
  cleaning_maintenance: "5  Cleaning and maintenance",
  commissions: "6  Commissions",
  insurance: "7  Insurance",
  interest: "8  Interest",
  legal_professional: "9  Legal and professional fees",
  real_estate_taxes: "10  Real estate taxes",
  repairs: "11  Repairs",
  utilities: "12  Utilities",
  wages_salaries: "13  Wages and salaries",
  depreciation: "14  Depreciation",
  other_deductions: "17  Other deductions",
}

export const INCOME_ORDER = Object.keys(INCOME_LABELS)
export const EXPENSE_ORDER = Object.keys(EXPENSE_LABELS)
