(() => {
  "use strict";

  const tabs = [...document.querySelectorAll("[data-tab]")];
  const panels = [...document.querySelectorAll("[data-tab-panel]")];
  const validTabs = new Set(tabs.map((tab) => tab.dataset.tab));
  let mapController = null;

  function activateTab(name, { focus = false, scroll = false, updateHash = true } = {}) {
    const selectedName = validTabs.has(name) ? name : "overview";

    for (const tab of tabs) {
      const selected = tab.dataset.tab === selectedName;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    }
    for (const panel of panels) {
      panel.hidden = panel.dataset.tabPanel !== selectedName;
    }

    if (updateHash) {
      history.replaceState(null, "", `#${selectedName}`);
    }
    if (scroll) {
      document.querySelector(".product-tabs")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
    if (selectedName === "map") {
      window.setTimeout(() => {
        if (!mapController) mapController = createRequestMap();
        mapController?.show();
      }, 0);
    }
    if (selectedName === "pipeline") {
      const diagram = document.querySelector("[data-pipeline-diagram]");
      if (diagram && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        diagram.classList.remove("is-running");
        requestAnimationFrame(() => diagram.classList.add("is-running"));
      }
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab, { scroll: true }));
    tab.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = index;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      activateTab(tabs[nextIndex].dataset.tab, { focus: true, scroll: true });
    });
  });

  window.addEventListener("hashchange", () => {
    activateTab(window.location.hash.slice(1), { updateHash: false });
  });

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, value);
    }
    return element;
  }

  function linePath(rows, valueKey, x, y) {
    return rows
      .map((row, index) => `${index ? "L" : "M"}${x(index)} ${y(row[valueKey])}`)
      .join(" ");
  }

  function renderTrendChart() {
    const chart = document.querySelector("[data-trend-chart]");
    const payload = document.querySelector("#houston-trend-data");
    if (!chart || !payload) return;

    const rows = JSON.parse(payload.textContent);
    if (!rows.length) {
      chart.textContent = "No daily activity is available for this period.";
      return;
    }

    const width = 1000;
    const height = 360;
    const padding = { top: 28, right: 22, bottom: 48, left: 50 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const maximum = Math.max(...rows.flatMap((row) => [row.request_count, row.closed_request_count]), 1);
    const x = (index) => padding.left + (index / Math.max(rows.length - 1, 1)) * plotWidth;
    const y = (value) => padding.top + plotHeight - (value / maximum) * plotHeight;
    const svg = svgElement("svg", {
      viewBox: `0 0 ${width} ${height}`,
      "aria-hidden": "true",
      preserveAspectRatio: "xMidYMid meet",
    });

    for (let index = 0; index <= 4; index += 1) {
      const value = Math.round((maximum * index) / 4);
      const gridY = y(value);
      svg.append(svgElement("line", {
        x1: padding.left,
        x2: width - padding.right,
        y1: gridY,
        y2: gridY,
        class: "trend-grid",
      }));
      const label = svgElement("text", {
        x: padding.left - 10,
        y: gridY + 4,
        "text-anchor": "end",
        class: "trend-axis-label",
      });
      label.textContent = value.toLocaleString();
      svg.append(label);
    }

    const requestPath = linePath(rows, "request_count", x, y);
    const closedPath = linePath(rows, "closed_request_count", x, y);
    const areaPath = `${requestPath} L${x(rows.length - 1)} ${padding.top + plotHeight} L${x(0)} ${padding.top + plotHeight} Z`;
    svg.append(svgElement("path", { d: areaPath, class: "trend-area" }));
    svg.append(svgElement("path", { d: requestPath, class: "trend-line-request" }));
    svg.append(svgElement("path", { d: closedPath, class: "trend-line-closed" }));

    const pointInterval = Math.max(Math.ceil(rows.length / 12), 1);
    rows.forEach((row, index) => {
      if (index % pointInterval === 0 || index === rows.length - 1) {
        svg.append(svgElement("circle", {
          cx: x(index),
          cy: y(row.request_count),
          r: 4,
          class: "trend-point",
        }));
      }
    });

    const labelIndexes = [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])];
    for (const index of labelIndexes) {
      const date = new Date(`${rows[index].request_date}T00:00:00`);
      const label = svgElement("text", {
        x: x(index),
        y: height - 15,
        "text-anchor": index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle",
        class: "trend-axis-label",
      });
      label.textContent = date.toLocaleDateString(undefined, {
        month: "short",
        year: rows.length > 90 ? "numeric" : undefined,
        day: rows.length > 90 ? undefined : "numeric",
      });
      svg.append(label);
    }
    chart.replaceChildren(svg);
  }

  function createRequestMap() {
    const mapElement = document.querySelector("[data-map]");
    const form = document.querySelector("[data-map-filters]");
    const count = document.querySelector("[data-map-count]");
    const note = document.querySelector("[data-map-note]");
    const cellCount = document.querySelector("[data-map-cell-count]");
    const openCount = document.querySelector("[data-map-open-count]");
    const selectionCount = document.querySelector("[data-map-selection-count]");
    const selectionDetail = document.querySelector("[data-map-selection-detail]");
    const selectionDate = document.querySelector("[data-map-selection-date]");
    const selectionBreakdown = document.querySelector("[data-map-selection-breakdown]");
    const selectionChart = document.querySelector("[data-map-selection-chart]");
    const selectionTypes = document.querySelector("[data-map-selection-types]");
    if (
      !mapElement || !form || !count || !note || !cellCount || !openCount ||
      !selectionCount || !selectionDetail || !selectionDate || !selectionBreakdown ||
      !selectionChart || !selectionTypes
    ) return null;
    if (!window.L) {
      count.textContent = "Unavailable";
      note.textContent = "The request map could not be initialized. Try refreshing the page.";
      return { show() {} };
    }

    const map = window.L.map(mapElement, {
      center: [29.76, -95.37],
      zoom: 10,
      minZoom: 8,
    });
    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(map);

    const requestLayer = window.L.layerGroup().addTo(map);
    const styles = getComputedStyle(document.documentElement);
    const primaryColor = styles.getPropertyValue("--site-primary");
    const secondaryColor = styles.getPropertyValue("--site-secondary");
    const warningColor = styles.getPropertyValue("--site-warning");
    const breakdownColors = [
      styles.getPropertyValue("--site-dark-link"),
      styles.getPropertyValue("--site-warning"),
      styles.getPropertyValue("--site-accent"),
      styles.getPropertyValue("--site-dark-control-border"),
      styles.getPropertyValue("--site-secondary"),
    ];
    let features = [];
    let selectedLayer = null;
    let selectedStyle = null;

    function replaceFilterOptions(name, options, allLabel) {
      const select = form.elements.namedItem(name);
      if (!(select instanceof HTMLSelectElement)) return false;

      const selectedValue = select.value;
      const allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = allLabel;
      const availableOptions = options.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        return option;
      });
      select.replaceChildren(allOption, ...availableOptions);
      select.disabled = options.length === 0;
      if (selectedValue && options.includes(selectedValue)) {
        select.value = selectedValue;
        return false;
      }
      return Boolean(selectedValue);
    }

    function renderSelectionBreakdown(requestTypes) {
      const total = requestTypes.reduce((sum, item) => sum + item.request_count, 0);
      if (!total) {
        selectionBreakdown.hidden = true;
        return;
      }

      let share = 0;
      const segments = requestTypes.map((item, index) => {
        const start = share;
        share += (item.request_count / total) * 100;
        return `${breakdownColors[index % breakdownColors.length]} ${start}% ${share}%`;
      });
      selectionChart.style.background = `conic-gradient(${segments.join(", ")})`;
      selectionChart.setAttribute(
        "aria-label",
        `Request type breakdown: ${requestTypes.map((item) => `${item.label}, ${item.request_count}`).join("; ")}`,
      );
      selectionTypes.replaceChildren(
        ...requestTypes.map((item, index) => {
          const row = document.createElement("li");
          const swatch = document.createElement("i");
          const label = document.createElement("span");
          const value = document.createElement("b");
          swatch.style.setProperty("--swatch", breakdownColors[index % breakdownColors.length]);
          label.textContent = item.label;
          value.textContent = item.request_count.toLocaleString();
          row.append(swatch, label, value);
          return row;
        }),
      );
      selectionBreakdown.hidden = false;
    }

    function renderRequests() {
      requestLayer.clearLayers();
      selectedLayer = null;
      selectedStyle = null;
      selectionCount.textContent = "Select a cell";
      selectionDetail.textContent = "Choose a shaded cell to inspect its request volume and open work.";
      selectionDate.textContent = "";
      selectionBreakdown.hidden = true;
      selectionChart.removeAttribute("style");
      selectionChart.removeAttribute("aria-label");
      selectionTypes.replaceChildren();
      const maximum = Math.max(
        ...features.map((feature) => feature.properties.request_count),
        1,
      );

      for (const feature of features) {
        const [longitude, latitude] = feature.geometry.coordinates;
        const properties = feature.properties;
        const intensity = Math.log1p(properties.request_count) / Math.log1p(maximum);
        const baseStyle = {
          color: primaryColor,
          fillColor: secondaryColor,
          fillOpacity: 0.12 + intensity * 0.7,
          opacity: 0.35,
          weight: 0.75,
        };
        const layer = window.L.rectangle(
          [
            [latitude - 0.005, longitude - 0.005],
            [latitude + 0.005, longitude + 0.005],
          ],
          baseStyle,
        );
        const requestLabel = properties.request_count === 1 ? "request" : "requests";
        const openRate = Math.round(
          (properties.open_request_count / properties.request_count) * 100,
        );
        layer.bindTooltip(
          `${properties.request_count.toLocaleString()} ${requestLabel} · ${properties.open_request_count.toLocaleString()} open`,
          { direction: "top", opacity: 0.96, sticky: true },
        );
        layer.on({
          click() {
            if (selectedLayer && selectedStyle) selectedLayer.setStyle(selectedStyle);
            selectedLayer = layer;
            selectedStyle = baseStyle;
            layer.setStyle({ color: warningColor, opacity: 1, weight: 3 });
            layer.bringToFront();
            selectionCount.textContent = `${properties.request_count.toLocaleString()} ${requestLabel}`;
            selectionDetail.textContent = `${properties.open_request_count.toLocaleString()} open · ${openRate}% of this cell`;
            selectionDate.textContent = `Latest request ${new Date(properties.latest_request_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            })}`;
            renderSelectionBreakdown(properties.request_types);
          },
          mouseover() {
            if (selectedLayer !== layer) layer.setStyle({ opacity: 0.9, weight: 1.5 });
          },
          mouseout() {
            if (selectedLayer !== layer) layer.setStyle(baseStyle);
          },
        });
        layer.addTo(requestLayer);
      }
    }

    let abortController = null;
    async function loadRequests() {
      abortController?.abort();
      abortController = new AbortController();
      count.textContent = "Loading…";
      note.textContent = "Querying Houston 311 activity.";
      cellCount.textContent = "—";
      openCount.textContent = "—";
      const parameters = new URLSearchParams();
      for (const [key, value] of new FormData(form).entries()) {
        if (value) parameters.set(key, value);
      }

      try {
        const response = await fetch(`${mapElement.dataset.endpoint}?${parameters}`, {
          headers: { Accept: "application/json" },
          signal: abortController.signal,
        });
        if (!response.ok) throw new Error(`Map request failed with ${response.status}`);
        const data = await response.json();
        const invalidSelection = [
          replaceFilterOptions("status", data.filters.statuses, "All request statuses"),
          replaceFilterOptions("district", data.filters.districts, "All districts"),
          replaceFilterOptions("case_type", data.filters.request_types, "All request types"),
        ].some(Boolean);
        if (invalidSelection) {
          loadRequests();
          return;
        }
        features = data.features;
        renderRequests();
        count.textContent = data.matching_request_count.toLocaleString();
        cellCount.textContent = data.features.length.toLocaleString();
        openCount.textContent = data.open_request_count.toLocaleString();
        note.textContent = data.features.length
          ? "Shading shows relative request concentration in the filtered result."
          : "No mapped requests match these filters.";
        if (data.features.length) {
          const bounds = window.L.latLngBounds(
            data.features.map((feature) => {
              const [longitude, latitude] = feature.geometry.coordinates;
              return [latitude, longitude];
            }),
          );
          map.fitBounds(bounds, { padding: [24, 24], maxZoom: 12 });
        } else {
          map.setView([29.76, -95.37], 10);
        }
      } catch (error) {
        if (error.name === "AbortError") return;
        count.textContent = "Unavailable";
        note.textContent = "The request map could not be loaded. Try changing the filters or refreshing the page.";
      }
    }

    form.addEventListener("change", loadRequests);
    form.querySelector("[data-map-reset]")?.addEventListener("click", () => {
      form.reset();
      loadRequests();
    });
    loadRequests();

    return {
      show() {
        map.invalidateSize();
      },
    };
  }

  renderTrendChart();
  activateTab(window.location.hash.slice(1), { updateHash: false });
})();
