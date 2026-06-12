/* ================================================================
   SPECTRE Public Logbook — standalone page logic
   ================================================================ */

(function () {
    "use strict";

    var logTableBody = document.querySelector("#log-table tbody");
    var refreshBtn = document.getElementById("refresh-logs-btn");
    var downloadCsvBtn = document.getElementById("download-csv-btn");
    var logsStatus = document.getElementById("logs-status");
    var logFilter = document.getElementById("log-filter");

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

    function showStatus(msg, isError) {
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

    function refreshLogs() {
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

    logFilter.addEventListener("keyup", applyFilter);
    refreshBtn.addEventListener("click", refreshLogs);

    // ---- Column sorting (data rows keep their detail rows attached) ----
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

    // ---- Admin CSV download ----
    downloadCsvBtn.addEventListener("click", function () {
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
    });

    refreshLogs();
})();
