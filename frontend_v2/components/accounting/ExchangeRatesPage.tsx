import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatNumber } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import { useConfirm } from "../../contexts/ConfirmContext";
import type { ExchangeRateDto, CurrencyDto } from "../../types/accounting";
import {
  KitDocumentShell,
  KitDenseTable,
} from "../kit";
import type { KitToolbarAction, KitTab, DenseColumn } from "../kit";
import { Plus, Trash2 } from "lucide-react";

export const ExchangeRatesPage: React.FC = () => {
  const [rates, setRates] = useState<ExchangeRateDto[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();

  const [fromCur, setFromCur] = useState("");
  const [toCur, setToCur] = useState("");
  const [rate, setRate] = useState("");
  const [effDate, setEffDate] = useState(
    new Date().toISOString().split("T")[0]
  );

  // Currency filter
  const [filterCurrency, setFilterCurrency] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [r, c] = await Promise.all([
        accountingApi.getExchangeRates(),
        accountingApi.getCurrencies(),
      ]);
      setRates(r as ExchangeRateDto[]);
      setCurrencies(c as CurrencyDto[]);
      if (!fromCur && c.length > 0) {
        const usd = (c as CurrencyDto[]).find((x) => x.Code === "USD");
        const ils = (c as CurrencyDto[]).find((x) => x.IsBaseCurrency);
        if (usd) setFromCur(String(usd.CurrencyID));
        if (ils) setToCur(String(ils.CurrencyID));
      }
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addRate = async () => {
    if (!fromCur || !toCur || !rate || !effDate) return;
    if (fromCur === toCur) {
      setErr("لا يمكن اختيار نفس العملة");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.createExchangeRate({
        from_currency: Number(fromCur),
        to_currency: Number(toCur),
        rate: parseFloat(rate),
        effective_date: effDate,
      });
      setRate("");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    } finally {
      setBusy(false);
    }
  };

  const deleteRate = async (id: number) => {
    if (!(await confirm({ message: "حذف سعر الصرف؟" }))) return;
    setBusy(true);
    try {
      await accountingApi.deleteExchangeRate(id);
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (d: string) => {
    const [y, m, day] = d.split("-");
    return `${day}/${m}/${y}`;
  };

  const getCurrencyLabel = (id: number) => {
    const c = currencies.find((x) => x.CurrencyID === id);
    return c ? `${c.Code}${c.Name ? ` — ${c.Name}` : ""}` : String(id);
  };

  const filteredRates = filterCurrency
    ? rates.filter((r) =>
        String(r.from_currency) === filterCurrency ||
        String(r.to_currency) === filterCurrency
      )
    : rates;

  const columns: DenseColumn<ExchangeRateDto>[] = [
    {
      key: "from_currency", header: "من عملة",
      render: (r) => r.from_currency_code || getCurrencyLabel(r.from_currency),
    },
    {
      key: "to_currency", header: "إلى عملة",
      render: (r) => r.to_currency_code || getCurrencyLabel(r.to_currency),
    },
    {
      key: "rate", header: "السعر", numeric: true,
      render: (r) => formatNumber(r.rate, { maxDecimals: 6 }),
    },
    {
      key: "effective_date", header: "تاريخ السريان",
      render: (r) => fmtDate(r.effective_date),
    },
    {
      key: "delete", header: "حذف",
      render: (r) => (
        <button
          type="button"
          className="ktra-toolbtn ktra-toolbtn--danger"
          disabled={busy}
          onClick={(e) => { e.stopPropagation(); deleteRate(r.id); }}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      ),
    },
  ];

  const actions: KitToolbarAction[] = [
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  const headerBand = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="ktra-field">
        <label className="ktra-field-label">من عملة</label>
        <select className="ktra-input" value={fromCur} onChange={(e) => setFromCur(e.target.value)}>
          <option value="">—</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}{c.Name ? ` — ${c.Name}` : ""}</option>
          ))}
        </select>
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">إلى عملة</label>
        <select className="ktra-input" value={toCur} onChange={(e) => setToCur(e.target.value)}>
          <option value="">—</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}{c.Name ? ` — ${c.Name}` : ""}</option>
          ))}
        </select>
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">سعر الصرف</label>
        <input type="number" step="0.000001" className="ktra-input ktra-num"
          style={{ width: "120px" }} placeholder="3.650000"
          value={rate} onChange={(e) => setRate(e.target.value)} />
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">تاريخ السريان</label>
        <input type="date" className="ktra-input" value={effDate} onChange={(e) => setEffDate(e.target.value)} />
      </div>
      <button type="button" className="ktra-toolbtn" disabled={busy || !fromCur || !toCur || !rate}
        onClick={addRate} style={{ marginTop: "18px" }}>
        <Plus className="w-4 h-4" />إضافة
      </button>
      <div style={{ flex: "1" }} />
      <div className="ktra-field" style={{ minWidth: "160px" }}>
        <label className="ktra-field-label">تصفية حسب عملة</label>
        <select className="ktra-input" value={filterCurrency} onChange={(e) => setFilterCurrency(e.target.value)}>
          <option value="">الكل</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>
          ))}
        </select>
      </div>
    </div>
  );

  const tableContent = (
    <>
      {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <KitDenseTable<ExchangeRateDto>
        columns={columns}
        rows={filteredRates}
        getRowKey={(r) => r.id}
        loading={loading}
        emptyHint="لا توجد أسعار صرف"
      />
    </>
  );

  const tabs: KitTab[] = [
    { key: "rates", label: "أسعار الصرف", content: tableContent },
  ];

  return (
    <div>
      <KitDocumentShell
        title="أسعار الصرف"
        actions={actions}
        header={headerBand}
        tabs={tabs}
        status={
          <span className="ktra-status-item">{filteredRates.length} سعر</span>
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};
