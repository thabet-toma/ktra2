p = 'sales/services.py'
with open(p, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the function definition
start = None
for i, ln in enumerate(lines):
    if ln.startswith('def _build_cogs_journal_line_dicts'):
        start = i
        break

assert start is not None, 'func not found'
# Find 'pair_totals[(cat.cogs_account_id' line within function (that's the last line before we cut)
cut_start = None
cut_end = None
for i in range(start, min(start + 60, len(lines))):
    if 'pair_totals: dict[tuple[int, int], Decimal]' in lines[i]:
        cut_start = i
    if 'pair_totals[(cat.cogs_account_id, cat.inventory_account_id)] += amt' in lines[i]:
        cut_end = i
        break

assert cut_start is not None and cut_end is not None, f'boundaries not found: {cut_start}/{cut_end}'

print('cut', cut_start, cut_end)
print('start line:', repr(lines[cut_start]))
print('end line:', repr(lines[cut_end]))

new_block = [
    "    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()\n",
    "    fb_cogs = ss.default_cogs_account_id if ss else None\n",
    "    fb_inv = ss.default_inventory_account_id if ss else None\n",
    "\n",
    "    pair_totals: dict[tuple[int, int], Decimal] = defaultdict(Decimal)\n",
    "    for line in lines:\n",
    "        p = products_by_id[line.product_id]\n",
    "        if getattr(p, 'is_service', False):\n",
    "            continue\n",
    "        qty = Decimal(str(line.quantity))\n",
    "        avg = Decimal(str(p.avg_cost))\n",
    "        amt = (qty * avg).quantize(DEC)\n",
    "        if amt <= 0:\n",
    "            continue\n",
    "        cat = p.category\n",
    "        cogs_id = cat.cogs_account_id if cat and cat.cogs_account_id else fb_cogs\n",
    "        inv_id = cat.inventory_account_id if cat and cat.inventory_account_id else fb_inv\n",
    "        if not cogs_id or not inv_id:\n",
    "            cname = cat.name if cat else \"(\u0628\u062f\u0648\u0646 \u0641\u0626\u0629)\"\n",
    "            raise ValidationError(\n",
    "                f\"\u0627\u0644\u0635\u0646\u0641 \u00ab{p.sku}\u00bb \u2014 \u0627\u0644\u0641\u0626\u0629 \u00ab{cname}\u00bb: \u0639\u064a\u0651\u0646 \u062d\u0633\u0627\u0628 \u062a\u0643\u0644\u0641\u0629 \u0627\u0644\u0645\u0628\u064a\u0639\u0627\u062a \u0648\u0627\u0644\u0645\u062e\u0632\u0648\u0646 \u0641\u064a \u0641\u0626\u0629 \u0627\u0644\u0645\u0646\u062a\u062c \"\n",
    "                f\"\u0623\u0648 \u062d\u0633\u0627\u0628\u0627\u062a \u0627\u0641\u062a\u0631\u0627\u0636\u064a\u0629 \u0641\u064a \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0645\u0628\u064a\u0639\u0627\u062a\u060c \u0623\u0648 \u0639\u0637\u0651\u0644 \u062e\u0635\u0645 \u0627\u0644\u0645\u062e\u0632\u0648\u0646 \u0639\u0646\u062f \u0627\u0644\u062a\u0631\u062d\u064a\u0644.\"\n",
    "            )\n",
    "        pair_totals[(cogs_id, inv_id)] += amt\n",
]

new_lines = lines[:cut_start] + new_block + lines[cut_end + 1:]
with open(p, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('DONE')
