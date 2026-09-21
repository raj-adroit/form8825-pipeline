export interface LineItem {
  id: number
  key: string
  value: number
  source: "extracted" | "manual"
  updated_at: string
}

export interface Totals {
  total_rental_income: number
  total_expenses: number
  net_income: number
}

export interface Property {
  id: number
  property_name: string
  property_address: string
  income_line_items: Record<string, LineItem>
  expense_line_items: Record<string, LineItem>
  totals: Totals
}

export interface Document {
  id: number
  filename: string
  uploaded_at: string
  warnings: string[]
  properties: Property[]
  grand_total_net_income: number
}

export interface DocumentSummary {
  id: number
  filename: string
  uploaded_at: string
  property_count: number
}

export interface LineItemChange {
  id: number
  old_value: number | null
  new_value: number
  changed_by: string
  note: string | null
  changed_at: string
}
