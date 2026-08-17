(() => {
  "use strict";

  const workspace = document.querySelector("[data-invoice-workspace]");
  const uploadForm = document.querySelector("[data-invoice-upload-form]");
  if (!workspace || !uploadForm) return;

  const fileInput = uploadForm.querySelector("[data-invoice-file]");
  const fileLabel = uploadForm.querySelector("[data-invoice-file-label]");
  const dropZone = uploadForm.querySelector("[data-invoice-drop-zone]");
  const resultPanel = workspace.querySelector("[data-invoice-result]");
  const statusPanel = resultPanel.querySelector("[data-invoice-status]");
  const tabs = [...resultPanel.querySelectorAll("[data-invoice-tab]")];
  const tabList = resultPanel.querySelector("[data-invoice-tabs]");
  const panels = [...resultPanel.querySelectorAll("[data-invoice-panel]")];
  const demoButtons = [...workspace.querySelectorAll("[data-invoice-demo]")];
  const pdfWorkspace = resultPanel.querySelector("[data-invoice-pdf-workspace]");
  const desktopPdfMount = resultPanel.querySelector("[data-invoice-pdf-desktop-mount]");
  const mobilePdfMount = resultPanel.querySelector("[data-invoice-pdf-mobile-mount]");
  const pdfFrame = resultPanel.querySelector("[data-invoice-pdf-frame]");
  const previewPlaceholder = resultPanel.querySelector("[data-invoice-preview-placeholder]");
  const sourceLink = resultPanel.querySelector("[data-invoice-source-pdf]");
  const mobileLayout = window.matchMedia("(max-width: 1050px)");
  let ownedPdfUrl = null;
  let progressStartedAt = 0;
  let progressTimer = null;
  let extractionRunning = false;
  const initialPollDelayMilliseconds = 2000;
  const maximumPollDelayMilliseconds = 10000;
  const pollBackoffMultiplier = 1.6;
  const missingValueLabel = "-";
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

  const progressStages = [
    {
      afterSeconds: 0,
      title: "Starting secure extraction",
      detail: "Validating the upload and starting an isolated document worker.",
    },
    {
      afterSeconds: 10,
      title: "Scanning and reading the PDF",
      detail: "The managed worker is checking the file, then extracting layout, tables, and text.",
    },
    {
      afterSeconds: 45,
      title: "Still reading the document",
      detail: "Cold model startup is slower; the PDF will remain available while processing continues.",
    },
    {
      afterSeconds: 70,
      title: "Validating extracted fields",
      detail: "The invoice agent is returning a typed response and reconciling printed totals.",
    },
  ];

  function isMissing(value) {
    return value === null || value === undefined || value === "";
  }

  function formatCurrency(value, currency) {
    if (isMissing(value)) return null;
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(Number(value));
  }

  function formatDate(value) {
    if (isMissing(value)) return null;
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return String(value);
    return dateFormatter.format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))));
  }

  function setText(selector, value) {
    const element = resultPanel.querySelector(selector);
    const missing = isMissing(value);
    element.textContent = missing ? missingValueLabel : String(value);
    element.classList.toggle("is-empty", missing);
  }

  function setControlsDisabled(disabled) {
    fileInput.disabled = disabled;
    demoButtons.forEach((button) => { button.disabled = disabled; });
  }

  function responseErrorMessage(detail, fallback) {
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => item?.msg).filter(Boolean);
      if (messages.length) return messages.join(" ");
    }
    if (typeof detail?.message === "string") return detail.message;
    return fallback;
  }

  function setPdfSource(url, filename, openUrl = url, ownsUrl = false) {
    if (ownedPdfUrl && ownedPdfUrl !== url) URL.revokeObjectURL(ownedPdfUrl);
    ownedPdfUrl = ownsUrl ? url : null;
    sourceLink.href = openUrl;
    setText("[data-invoice-source-name]", filename);
    pdfFrame.src = url;
    pdfFrame.hidden = false;
    previewPlaceholder.hidden = true;
  }

  function setActiveTab(name) {
    tabs.forEach((tab) => {
      const active = tab.dataset.invoiceTab === name;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.invoicePanel !== name;
    });
  }

  function syncPdfViewerLocation() {
    const target = mobileLayout.matches ? mobilePdfMount : desktopPdfMount;
    if (pdfWorkspace.parentElement !== target) target.append(pdfWorkspace);
    const selectedTab = tabs.find((tab) => tab.getAttribute("aria-selected") === "true");
    if (!mobileLayout.matches && selectedTab?.dataset.invoiceTab === "pdf") setActiveTab("data");
  }

  function updateProgress() {
    const elapsedSeconds = Math.floor((Date.now() - progressStartedAt) / 1000);
    const stage = [...progressStages].reverse().find(({ afterSeconds }) => elapsedSeconds >= afterSeconds);
    statusPanel.querySelector("[data-invoice-status-title]").textContent = stage.title;
    statusPanel.querySelector("[data-invoice-status-detail]").textContent = stage.detail;
    const minutes = Math.floor(elapsedSeconds / 60);
    const seconds = String(elapsedSeconds % 60).padStart(2, "0");
    statusPanel.querySelector("[data-invoice-status-elapsed]").textContent = `${minutes}:${seconds} elapsed`;
  }

  function startProgress() {
    if (progressTimer) window.clearInterval(progressTimer);
    progressStartedAt = Date.now();
    resultPanel.hidden = false;
    tabList.hidden = true;
    panels.forEach((panel) => { panel.hidden = true; });
    statusPanel.hidden = false;
    statusPanel.classList.remove("is-error");
    updateProgress();
    progressTimer = window.setInterval(updateProgress, 1000);
    resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function stopProgress() {
    if (progressTimer) window.clearInterval(progressTimer);
    progressTimer = null;
  }

  function showError(message) {
    stopProgress();
    tabList.hidden = true;
    panels.forEach((panel) => { panel.hidden = true; });
    statusPanel.hidden = false;
    statusPanel.classList.add("is-error");
    statusPanel.querySelector("[data-invoice-status-title]").textContent = "Extraction failed";
    statusPanel.querySelector("[data-invoice-status-detail]").textContent = message;
    statusPanel.querySelector("[data-invoice-status-elapsed]").textContent = "Choose another PDF or try again.";
  }

  function renderLineItems(invoice) {
    const container = resultPanel.querySelector("[data-invoice-line-items]");
    const items = invoice.line_items;
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "invoice-line-empty is-empty";
      empty.textContent = missingValueLabel;
      container.replaceChildren(empty);
      return;
    }

    const showDiscount = items.some((item) => !isMissing(item.discount));
    const showTax = items.some((item) => !isMissing(item.tax_rate) || !isMissing(item.tax_amount));
    const columns = [
      { key: "index", label: "#" },
      { key: "description", label: "Description" },
      { key: "qty", label: "Qty" },
      { key: "unit_price", label: "Unit price" },
    ];
    if (showDiscount) columns.push({ key: "discount", label: "Discount" });
    if (showTax) columns.push({ key: "tax", label: "Tax" });
    columns.push({ key: "line_total", label: "Line total" });

    const table = document.createElement("table");
    table.className = "invoice-line-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const column of columns) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column.label;
      headRow.append(th);
    }
    thead.append(headRow);

    const tbody = document.createElement("tbody");
    for (const [index, item] of items.entries()) {
      const row = document.createElement("tr");
      const quantity = isMissing(item.quantity)
        ? null
        : [item.quantity, item.unit].filter((part) => !isMissing(part)).join(" ");
      const taxParts = [
        isMissing(item.tax_rate) ? null : `${item.tax_rate}%`,
        formatCurrency(item.tax_amount, invoice.currency),
      ].filter(Boolean);
      const values = {
        index: String(index + 1).padStart(2, "0"),
        description: item.description,
        qty: quantity,
        unit_price: formatCurrency(item.unit_price, invoice.currency),
        discount: formatCurrency(item.discount, invoice.currency),
        tax: taxParts.length ? taxParts.join(" · ") : null,
        line_total: formatCurrency(item.line_total, invoice.currency),
      };
      for (const column of columns) {
        const value = values[column.key];
        const empty = column.key !== "index" && column.key !== "description" && isMissing(value);
        const cell = document.createElement("td");
        cell.textContent = empty ? missingValueLabel : String(value);
        cell.classList.toggle("is-empty", empty);
        row.append(cell);
      }
      tbody.append(row);
    }

    table.append(thead, tbody);
    container.replaceChildren(table);
  }

  function updateGroupCounts() {
    for (const group of resultPanel.querySelectorAll("[data-invoice-field-group]")) {
      const count = group.querySelector("[data-invoice-group-found]");
      if (!count) continue;
      if (group.querySelector("[data-invoice-line-items]")) {
        const rows = group.querySelectorAll(".invoice-line-table tbody tr");
        count.textContent = rows.length ? String(rows.length) : "0";
        continue;
      }
      const values = [...group.querySelectorAll("dd")];
      const found = values.filter((value) => !value.classList.contains("is-empty")).length;
      count.textContent = `${found}/${values.length}`;
    }
  }

  function renderExtraction(payload) {
    stopProgress();
    const invoice = payload.invoice;
    const supplier = payload.supplier_match;
    const isDemo = payload.demo === true;
    const buyer = invoice.buyer || {};
    const documentId = isDemo ? "Pre-parsed public demo" : payload.document_id;
    const supplierStatus = resultPanel.querySelector("[data-invoice-supplier-status]");

    setText("[data-invoice-seller]", invoice.seller.name);
    setText("[data-invoice-number]", invoice.invoice_number);
    setText("[data-invoice-issued]", formatDate(invoice.issue_date));
    setText("[data-invoice-total]", formatCurrency(invoice.total, invoice.currency));
    setText("[data-invoice-document-id]", documentId);
    setText("[data-invoice-due]", formatDate(invoice.due_date));
    setText("[data-invoice-po]", invoice.purchase_order_number);
    setText("[data-invoice-terms]", invoice.payment_terms);
    setText("[data-invoice-currency]", invoice.currency);
    setText("[data-invoice-seller-name]", invoice.seller.name);
    setText("[data-invoice-seller-address]", invoice.seller.address);
    setText("[data-invoice-seller-tax-id]", invoice.seller.tax_id);
    setText("[data-invoice-supplier-status]", supplier ? "Matched" : "Needs review");
    supplierStatus.dataset.state = supplier ? "matched" : "review";
    setText("[data-invoice-supplier-id]", supplier?.supplier_id);
    setText("[data-invoice-supplier-name]", supplier?.name);
    setText("[data-invoice-buyer-name]", buyer.name);
    setText("[data-invoice-buyer-address]", buyer.address);
    setText("[data-invoice-buyer-tax-id]", buyer.tax_id);
    setText("[data-invoice-subtotal]", formatCurrency(invoice.subtotal, invoice.currency));
    setText("[data-invoice-discount]", formatCurrency(invoice.discount_total, invoice.currency));
    setText("[data-invoice-shipping]", formatCurrency(invoice.shipping_total, invoice.currency));
    setText("[data-invoice-tax]", formatCurrency(invoice.tax_total, invoice.currency));
    setText("[data-invoice-total-detail]", formatCurrency(invoice.total, invoice.currency));
    renderLineItems(invoice);
    updateGroupCounts();

    resultPanel.querySelector("[data-invoice-result-description]").textContent = isDemo
      ? "This committed fixture is already parsed so you can inspect its source, typed data, and text immediately."
      : "Compare the validated Pydantic response with the source PDF and Docling text used for extraction.";
    resultPanel.querySelector("[data-invoice-ocr]").textContent = payload.document_markdown;
    if (!isDemo && payload.document_url) {
      setPdfSource(
        payload.document_url,
        resultPanel.querySelector("[data-invoice-source-name]").textContent,
      );
    }
    resultPanel.querySelector("[data-invoice-json]").textContent = JSON.stringify(
      isDemo
        ? { invoice, supplier_match: supplier }
        : {
          document_id: payload.document_id,
          invoice,
          supplier_match: supplier,
          all_agent_messages: payload.all_agent_messages,
        },
      null,
      2,
    );
    statusPanel.hidden = true;
    tabList.hidden = false;
    setActiveTab(mobileLayout.matches ? "pdf" : "data");
  }

  function selectLocalFile(file) {
    if (!file) return;
    fileLabel.textContent = file.name;
    const url = URL.createObjectURL(file);
    setPdfSource(url, file.name, url, true);
  }

  async function waitForExtraction(job) {
    const deadline = Date.now() + 10 * 60 * 1000;
    const statusUrl = new URL(`${uploadForm.action}/${job.flow_run_id}`);
    statusUrl.searchParams.set("document_id", job.document_id);
    statusUrl.searchParams.set("access_token", job.access_token);
    let delayMilliseconds = initialPollDelayMilliseconds;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, delayMilliseconds));
      const response = await fetch(statusUrl, { cache: "no-store" });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 202) {
        const retryAfterSeconds = Number(response.headers.get("Retry-After"));
        const retryAfterMilliseconds = Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
          ? retryAfterSeconds * 1000
          : initialPollDelayMilliseconds;
        delayMilliseconds = Math.max(
          retryAfterMilliseconds,
          Math.min(delayMilliseconds * pollBackoffMultiplier, maximumPollDelayMilliseconds),
        );
        continue;
      }
      if (!response.ok) {
        throw new Error(responseErrorMessage(payload.detail, "Invoice extraction failed."));
      }
      return payload;
    }
    throw new Error("Invoice extraction is still running. Try again in a few minutes.");
  }

  async function extractLocalFile(file) {
    if (!file || extractionRunning) return;
    const suppliedPasscode = window.prompt("Enter the invoice processing access code.");
    if (suppliedPasscode === null) {
      fileInput.value = "";
      return;
    }
    const passcode = suppliedPasscode.trim();
    if (!passcode) {
      fileInput.value = "";
      showError("Enter the invoice processing access code to upload a PDF.");
      return;
    }
    extractionRunning = true;
    selectLocalFile(file);
    const formData = new FormData(uploadForm);
    formData.set("passcode", passcode);
    setControlsDisabled(true);
    startProgress();
    try {
      const response = await fetch(uploadForm.action, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(responseErrorMessage(payload.detail, "Invoice extraction failed."));
      }
      renderExtraction(await waitForExtraction(payload));
    } catch (error) {
      showError(error.message);
    } finally {
      extractionRunning = false;
      setControlsDisabled(false);
    }
  }

  fileInput.addEventListener("change", () => {
    void extractLocalFile(fileInput.files[0]);
  });

  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  }
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-dragging"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const files = new DataTransfer();
    files.items.add(file);
    fileInput.files = files.files;
    void extractLocalFile(file);
  });

  uploadForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void extractLocalFile(fileInput.files[0]);
  });

  for (const button of demoButtons) {
    button.addEventListener("click", async () => {
      setControlsDisabled(true);
      try {
        const response = await fetch(button.dataset.invoiceDemo);
        if (!response.ok) throw new Error("The demo invoice could not be loaded.");
        const payload = await response.json();
        const filename = payload.pdf_url.split("/").at(-1) || "demo-invoice.pdf";
        setPdfSource(payload.pdf_url, filename);
        resultPanel.hidden = false;
        renderExtraction(payload);
        resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        resultPanel.hidden = false;
        showError(error.message);
      } finally {
        setControlsDisabled(false);
      }
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setActiveTab(tab.dataset.invoiceTab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const availableTabs = tabs.filter((candidate) => mobileLayout.matches || candidate.dataset.invoiceTab !== "pdf");
      const index = availableTabs.indexOf(tab);
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextTab = availableTabs[(index + direction + availableTabs.length) % availableTabs.length];
      setActiveTab(nextTab.dataset.invoiceTab);
      nextTab.focus();
    });
  });

  mobileLayout.addEventListener("change", syncPdfViewerLocation);
  syncPdfViewerLocation();

  window.addEventListener("beforeunload", () => {
    if (ownedPdfUrl) {
      pdfFrame.src = "about:blank";
      URL.revokeObjectURL(ownedPdfUrl);
    }
  });
})();
