"""Import-pipeline domain layer (redesign M0+).

Feature-based, single-source-of-truth services for the Deal → Shipment →
Clearance → Transport → ImportInvoice path:

- stages.py          : the one guarded deal stage machine (no bulk .update bypass)
- allocation.py      : the single cost-allocation engine (CBM/KG, reconciling)
- shipment_builder.py: create_shipment_from_deals() — the deal→shipment action
- invoice_gen.py     : build/refresh ImportInvoice from engine output

Pure logic here stays ORM-light and Decimal-exact; views stay thin.
"""
