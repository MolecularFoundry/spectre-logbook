/* ================================================================
   SPECTRE Public Logbook — shared table logic.
   Used by the in-app Public Logs page and the standalone /public-logs
   page. Both share the same element IDs.
   ================================================================ */

window.SpectreLogs = (function () {
    "use strict";

    var COLUMNS = [
        { key: "timestamp", label: "Timestamp" },
        { key: "user", label: "User" },
        { key: "session", label: "Session" },
        { key: "proposal", label: "Proposal" },
        { key: "title", label: "Title" },
        { key: "kv", label: "kV" },
        { key: "modes", label: "Modes" },
        { key: "holders", label: "Holders" },
        { key: "report", label: "Report" },
    ];

    var initialized = false;
    var logTableBody, logFilter, logsStatus;

    function showStatus(msg, isError) {
        if (!logsStatus) return;
        logsStatus.textContent = msg;
        logsStatus.className = "status-msg " + (isError ? "error" : "success");
        if (!isError) {
            setTimeout(function () { logsStatus.textContent = ""; }, 5000);
        }
    }

    // Show the title only when it exists and differs from the proposal/project id.
    function displayTitle(row) {
        var title = (row.title || "").trim();
        var proposal = (row.proposal || "").trim();
        return title && title !== proposal ? title : "";
    }

    function buildDetail(row) {
        var detailTr = document.createElement("tr");
        detailTr.className = "detail-row";
        var td = document.createElement("td");
        td.colSpan = COLUMNS.length;
        var dl = document.createElement("dl");
        dl.className = "detail-grid";
        COLUMNS.forEach(function (col) {
            var value = col.key === "title" ? displayTitle(row) : (row[col.key] || "");
            var dt = document.createElement("dt");
            dt.textContent = col.label;
            var dd = document.createElement("dd");
            dd.textContent = value;
            dl.appendChild(dt);
            dl.appendChild(dd);
        });
        td.appendChild(dl);
        detailTr.appendChild(td);
        return detailTr;
    }

    function refresh() {
        if (!logTableBody) return;
        fetch("api/public-logs")
            .then(function (r) { return r.json(); })
            .then(function (rows) {
                logTableBody.innerHTML = "";
                rows.forEach(function (row) {
                    var tr = document.createElement("tr");
                    tr.className = "data-row";
                    COLUMNS.forEach(function (col) {
                        var td = document.createElement("td");
                        if (col.key === "report") td.className = "col-report";
                        td.textContent = col.key === "title" ? displayTitle(row) : (row[col.key] || "");
                        tr.appendChild(td);
                    });
                    var detailTr = buildDetail(row);
                    tr.addEventListener("click", function () {
                        var open = detailTr.classList.toggle("open");
                        tr.classList.toggle("expanded", open);
                    });
                    logTableBody.appendChild(tr);
                    logTableBody.appendChild(detailTr);
                });
                applyFilter();
                showStatus("Public logs refreshed (" + rows.length + " entries).", false);
            })
            .catch(function (err) {
                showStatus("Error loading logs: " + err, true);
            });
    }

    function applyFilter() {
        if (!logFilter || !logTableBody) return;
        var f = logFilter.value.toLowerCase();
        var dataRows = logTableBody.querySelectorAll("tr.data-row");
        dataRows.forEach(function (row) {
            var match = row.textContent.toLowerCase().indexOf(f) !== -1;
            row.style.display = match ? "" : "none";
            var detail = row.nextElementSibling;
            if (detail && detail.classList.contains("detail-row") && !match) {
                detail.classList.remove("open");
                row.classList.remove("expanded");
            }
        });
    }

    function downloadCsv() {
        var password = prompt("Enter admin password:");
        if (!password) return;

        fetch("api/admin-csv", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: password }),
        })
            .then(function (r) {
                if (!r.ok) {
                    return r.json().then(function (d) { throw new Error(d.error || "Access denied."); });
                }
                return r.blob();
            })
            .then(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url;
                a.download = "spectre_admin_log.csv";
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                showStatus("Admin CSV downloaded.", false);
            })
            .catch(function (err) {
                showStatus(err.message || "Download failed.", true);
            });
    }

    // Add a drag handle on each column's left border so users can widen a
    // column and read long values (e.g. the Report) inline without expanding
    // every row. Grabbing the border moves it under the cursor: dragging left
    // grows the column (and shrinks its left neighbour), dragging right does
    // the reverse — so the box appears to expand toward the drag direction.
    function enableColumnResize() {
        var ths = Array.prototype.slice.call(document.querySelectorAll("#log-table th"));
        ths.forEach(function (th, idx) {
            if (idx === 0) return; // first column has no left neighbour to trade width with
            var prevTh = ths[idx - 1];

            var handle = document.createElement("span");
            handle.className = "col-resizer";
            th.appendChild(handle);

            var startX, startWidth, prevStartWidth;

            function onMove(e) {
                var delta = e.pageX - startX;
                th.style.width = Math.max(40, startWidth - delta) + "px";
                prevTh.style.width = Math.max(40, prevStartWidth + delta) + "px";
            }

            function onUp() {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                document.body.classList.remove("col-resizing");
            }

            // Don't let the drag trigger the header's sort handler.
            handle.addEventListener("click", function (e) { e.stopPropagation(); });
            handle.addEventListener("mousedown", function (e) {
                e.preventDefault();
                e.stopPropagation();
                startX = e.pageX;
                startWidth = th.offsetWidth;
                prevStartWidth = prevTh.offsetWidth;
                document.body.classList.add("col-resizing");
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
            });
        });
    }

    // Wire handlers once, then (re)load the data. Safe to call repeatedly.
    function init() {
        if (initialized) {
            refresh();
            return;
        }
        logTableBody = document.querySelector("#log-table tbody");
        if (!logTableBody) return;
        logFilter = document.getElementById("log-filter");
        logsStatus = document.getElementById("logs-status");

        var refreshBtn = document.getElementById("refresh-logs-btn");
        var downloadCsvBtn = document.getElementById("download-csv-btn");

        if (logFilter) logFilter.addEventListener("keyup", applyFilter);
        if (refreshBtn) refreshBtn.addEventListener("click", refresh);
        if (downloadCsvBtn) downloadCsvBtn.addEventListener("click", downloadCsv);

        enableColumnResize();

        document.querySelectorAll("#log-table th").forEach(function (th, colIdx) {
            var ascending = true;
            th.addEventListener("click", function () {
                var dataRows = Array.from(logTableBody.querySelectorAll("tr.data-row"));
                dataRows.sort(function (a, b) {
                    var aText = a.cells[colIdx].textContent;
                    var bText = b.cells[colIdx].textContent;
                    return ascending ? aText.localeCompare(bText) : bText.localeCompare(aText);
                });
                ascending = !ascending;
                dataRows.forEach(function (row) {
                    var detail = row.nextElementSibling;
                    logTableBody.appendChild(row);
                    if (detail && detail.classList.contains("detail-row")) {
                        logTableBody.appendChild(detail);
                    }
                });
            });
        });

        initialized = true;
        refresh();
    }

    return { init: init, refresh: refresh };
})();
