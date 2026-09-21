import { EXPENSE_LABELS, EXPENSE_ORDER, INCOME_LABELS, INCOME_ORDER } from "../labels"
import { formatCurrency } from "../format"
import { LineItemRow } from "./LineItemRow"
import type { Property } from "../types"

interface Props {
  property: Property
  onLineItemSave: (lineItemId: number, newValue: number) => Promise<void>
}

export function PropertyCard({ property, onLineItemSave }: Props) {
  return (
    <section className="property-card">
      <header>
        <h2>Property {property.property_name}</h2>
        <span className="address">{property.property_address || "(no address)"}</span>
      </header>

      <table className="line-item-table">
        <tbody>
          <tr className="section-header">
            <td colSpan={4}>Income</td>
          </tr>
          {INCOME_ORDER.map((key) => {
            const item = property.income_line_items[key]
            if (!item) return null
            return (
              <LineItemRow key={item.id} label={INCOME_LABELS[key]} item={item} onSave={onLineItemSave} />
            )
          })}

          <tr className="section-header">
            <td colSpan={4}>Expenses</td>
          </tr>
          {EXPENSE_ORDER.map((key) => {
            const item = property.expense_line_items[key]
            if (!item) return null
            return (
              <LineItemRow key={item.id} label={EXPENSE_LABELS[key]} item={item} onSave={onLineItemSave} />
            )
          })}
        </tbody>
      </table>

      <table className="totals-table">
        <tbody>
          <tr>
            <td>Total rental income (2c)</td>
            <td>{formatCurrency(property.totals.total_rental_income)}</td>
          </tr>
          <tr>
            <td>Total expenses (18)</td>
            <td>{formatCurrency(property.totals.total_expenses)}</td>
          </tr>
          <tr className="net-income-row">
            <td>Net income (19)</td>
            <td>{formatCurrency(property.totals.net_income)}</td>
          </tr>
        </tbody>
      </table>
    </section>
  )
}
