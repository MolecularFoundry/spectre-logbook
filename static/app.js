/* ================================================================
   SPECTRE Logbook — client-side logic
   ================================================================ */

(function () {
    "use strict";

    // ---- Element references ----
    var tabs = document.querySelectorAll(".tab-btn");
    var pages = document.querySelectorAll(".page");

    // Login page
    var emailInput = document.getElementById("email-input");
    var nameInput = document.getElementById("name-input");
    var orcidInput = document.getElementById("orcid-input");
    var proposalBox = document.getElementById("proposal-box");
    var sessionInput = document.getElementById("session-input");
    var loginBtn = document.getElementById("login-btn");
    var loginStatus = document.getElementById("login-status");

    // Logbook page
    var recap = document.getElementById("recap");
    var holderOther = document.getElementById("holder-other");
    var annotate = document.getElementById("annotate");
    var report = document.getElementById("report");
    var updateBtn = document.getElementById("update-btn");
    var logoutBtn = document.getElementById("logout-btn");
    var logbookStatus = document.getElementById("logbook-status");

    // Public logs page
    var logTableBody = document.querySelector("#log-table tbody");
    var refreshBtn = document.getElementById("refresh-logs-btn");
    var refreshBtnBottom = document.getElementById("refresh-logs-btn-bottom");
    var downloadCsvBtn = document.getElementById("download-csv-btn");
    var logsStatus = document.getElementById("logs-status");

    // Logout modal
    var logoutModal = document.getElementById("logout-modal");
    var modalLoginBtn = document.getElementById("modal-login-btn");
    var modalLogsBtn = document.getElementById("modal-logs-btn");

    // Date display
    var dateLabel = document.getElementById("date-label");
    var now = new Date();
    dateLabel.textContent =
        String(now.getMonth() + 1).padStart(2, "0") + "/" +
        String(now.getDate()).padStart(2, "0") + "/" +
        String(now.getFullYear()).slice(-2);

    // ---- Page switching ----
    function switchPage(pageName) {
        tabs.forEach(function (t) {
            t.classList.toggle("active", t.dataset.page === pageName);
        });
        pages.forEach(function (p) {
            p.classList.toggle("active", p.id === "page-" + pageName);
        });
    }

    tabs.forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (btn.disabled) return;
            switchPage(btn.dataset.page);
        });
    });

    // ---- Helpers ----
    function showStatus(el, msg, isError) {
        el.textContent = msg;
        el.className = "status-msg " + (isError ? "error" : "success");
        if (!isError) {
            setTimeout(function () { el.textContent = ""; }, 5000);
        }
    }

    function getChecked(name) {
        var boxes = document.querySelectorAll('input[name="' + name + '"]:checked');
        return Array.from(boxes).map(function (b) { return b.value; });
    }

    function clearChecked(name) {
        document.querySelectorAll('input[name="' + name + '"]').forEach(function (b) {
            b.checked = false;
        });
    }

    function clearLoginForm() {
        emailInput.value = "";
        nameInput.value = "";
        orcidInput.value = "";
        sessionInput.value = "";
        proposalBox.innerHTML = '<option value="">-- enter email to load projects --</option>';
        loginStatus.textContent = "";
    }

    function clearLogbookForm() {
        clearChecked("kv");
        clearChecked("modes");
        clearChecked("holders");
        holderOther.value = "";
        annotate.value = "";
        report.value = "";
        recap.innerHTML = "<em>(user and project auto-filled after login)</em>";
        logbookStatus.textContent = "";
    }

    // ---- Email lookup (debounced) ----
    var emailTimer = null;

    emailInput.addEventListener("input", function () {
        clearTimeout(emailTimer);
        emailTimer = setTimeout(lookupEmail, 600);
    });

    emailInput.addEventListener("blur", function () {
        clearTimeout(emailTimer);
        lookupEmail();
    });

    function lookupEmail() {
        var email = emailInput.value.trim();
        if (!email || email.indexOf("@lbl.gov") === -1) return;

        fetch("api/lookup-email", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) {
                    showStatus(loginStatus, data.error || "Lookup failed.", true);
                    return;
                }
                nameInput.value = data.name || "";
                orcidInput.value = data.orcid || "";

                // Populate project dropdown (sorted alphabetically by code)
                proposalBox.innerHTML = "";
                if (data.proposals && data.proposals.length > 0) {
                    var sorted = data.proposals.slice().sort(function (a, b) {
                        return a.code.localeCompare(b.code);
                    });
                    sorted.forEach(function (p) {
                        var opt = document.createElement("option");
                        opt.value = p.code;
                        opt.textContent = p.title ? p.code + " \u2014 " + p.title : p.code;
                        proposalBox.appendChild(opt);
                    });
                } else {
                    var opt = document.createElement("option");
                    opt.value = "";
                    opt.textContent = "No projects found for this user.";
                    proposalBox.appendChild(opt);
                }
                showStatus(loginStatus, "User info loaded.", false);
            })
            .catch(function (err) {
                showStatus(loginStatus, "Lookup error: " + err, true);
            });
    }

    // ---- Project title fetch on dropdown change ----
    proposalBox.addEventListener("change", function () {
        var code = proposalBox.value;
        if (!code) return;

        fetch("api/proposal-title/" + encodeURIComponent(code))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.title) {
                    var sel = proposalBox.options[proposalBox.selectedIndex];
                    sel.textContent = data.code + " \u2014 " + data.title;
                }
            })
            .catch(function () { /* ignore */ });
    });

    // ---- Login ----
    loginBtn.addEventListener("click", function () {
        var email = emailInput.value.trim();
        var name = nameInput.value.trim();
        var sessionName = sessionInput.value.trim();

        if (!email) { showStatus(loginStatus, "Email is required.", true); return; }
        if (!name) { showStatus(loginStatus, "Name is required.", true); return; }
        if (!sessionName) { showStatus(loginStatus, "Session name is required.", true); return; }

        var proposalText = proposalBox.options[proposalBox.selectedIndex]
            ? proposalBox.options[proposalBox.selectedIndex].textContent
            : "";

        var payload = {
            email: email,
            user_name: name,
            orcid: orcidInput.value.trim(),
            proposal: proposalText,
            session_name: sessionName,
        };

        fetch("api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) {
                    showStatus(loginStatus, data.error || "Login failed.", true);
                    return;
                }
                var titleText = data.proposal_title ? " \u2014 " + data.proposal_title : "";
                recap.innerHTML =
                    "<b>User:</b> " + data.user_name + "<br>" +
                    "<b>Project:</b> " + data.proposal + titleText + "<br>" +
                    "<b>Email:</b> " + data.email + "<br>" +
                    "<b>Login Time:</b> " + data.login_time + "<br>" +
                    "<b>Session ID:</b> " + data.session_id;

                // Switch directly to logbook (no tab needed)
                switchPage("logbook");
                showStatus(logbookStatus, "Logged in. Session ID: " + data.session_id, false);
            })
            .catch(function (err) {
                showStatus(loginStatus, "Login error: " + err, true);
            });
    });

    // ---- Collect logbook form data ----
    function collectLogbookData() {
        return {
            kv: getChecked("kv"),
            modes: getChecked("modes"),
            holders: getChecked("holders"),
            holder_other: holderOther.value.trim(),
            annotate_private: annotate.value.trim(),
            report_public: report.value.trim(),
        };
    }

    // ---- Update metadata ----
    updateBtn.addEventListener("click", function () {
        var data = collectLogbookData();
        fetch("api/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(function (r) { return r.json(); })
            .then(function (result) {
                if (!result.ok) {
                    showStatus(logbookStatus, result.error, true);
                    return;
                }
                // Flash button green briefly
                var origText = updateBtn.textContent;
                updateBtn.textContent = "Saved!";
                updateBtn.classList.add("flash-success");
                setTimeout(function () {
                    updateBtn.textContent = origText;
                    updateBtn.classList.remove("flash-success");
                }, 1500);
                showStatus(logbookStatus, result.message, false);
            })
            .catch(function (err) {
                showStatus(logbookStatus, "Update error: " + err, true);
            });
    });

    // ---- Logout ----
    logoutBtn.addEventListener("click", function () {
        var data = collectLogbookData();
        fetch("api/logout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        })
            .then(function (r) { return r.json(); })
            .then(function (result) {
                if (!result.ok) {
                    showStatus(logbookStatus, result.error, true);
                    return;
                }

                // Reset both forms
                clearLogbookForm();
                clearLoginForm();

                // Show the logout modal
                logoutModal.style.display = "flex";
            })
            .catch(function (err) {
                showStatus(logbookStatus, "Logout error: " + err, true);
            });
    });

    // ---- Logout modal buttons ----
    modalLoginBtn.addEventListener("click", function () {
        logoutModal.style.display = "none";
        switchPage("login");
    });

    modalLogsBtn.addEventListener("click", function () {
        logoutModal.style.display = "none";
        switchPage("public-logs");
        refreshLogs();
    });

    // ---- Public logs: refresh ----
    function refreshLogs() {
        fetch("api/public-logs")
            .then(function (r) { return r.json(); })
            .then(function (rows) {
                logTableBody.innerHTML = "";
                rows.forEach(function (row) {
                    var tr = document.createElement("tr");
                    ["timestamp", "event", "user", "session", "proposal", "title", "kv", "modes", "holders", "report"]
                        .forEach(function (key) {
                            var td = document.createElement("td");
                            td.textContent = row[key] || "";
                            tr.appendChild(td);
                        });
                    logTableBody.appendChild(tr);
                });
                showStatus(logsStatus, "Public logs refreshed (" + rows.length + " entries).", false);
            })
            .catch(function (err) {
                showStatus(logsStatus, "Error loading logs: " + err, true);
            });
    }

    refreshBtn.addEventListener("click", refreshLogs);
    refreshBtnBottom.addEventListener("click", refreshLogs);

    // ---- Log filter ----
    var logFilter = document.getElementById("log-filter");
    logFilter.addEventListener("keyup", function () {
        var f = logFilter.value.toLowerCase();
        var rows = logTableBody.querySelectorAll("tr");
        rows.forEach(function (row) {
            row.style.display = row.textContent.toLowerCase().indexOf(f) !== -1 ? "" : "none";
        });
    });

    // ---- Column sorting ----
    document.querySelectorAll("#log-table th").forEach(function (th, colIdx) {
        var ascending = true;
        th.addEventListener("click", function () {
            var rows = Array.from(logTableBody.querySelectorAll("tr"));
            rows.sort(function (a, b) {
                var aText = a.cells[colIdx].textContent;
                var bText = b.cells[colIdx].textContent;
                return ascending ? aText.localeCompare(bText) : bText.localeCompare(aText);
            });
            ascending = !ascending;
            rows.forEach(function (row) { logTableBody.appendChild(row); });
        });
    });

    // ---- Upload links (pass email + project as query params) ----
    var uploadTab = document.getElementById("upload-tab");
    var uploadBtn = document.getElementById("upload-btn");

    function buildUploadUrl() {
        var base = "http://localhost:5000";
        var params = [];
        var email = emailInput.value.trim();
        var project = proposalBox.value || "";
        if (email) params.push("email=" + encodeURIComponent(email));
        if (project) params.push("project=" + encodeURIComponent(project));
        return params.length ? base + "?" + params.join("&") : base;
    }

    uploadTab.addEventListener("click", function () {
        uploadTab.href = buildUploadUrl();
    });

    uploadBtn.addEventListener("click", function () {
        uploadBtn.href = buildUploadUrl();
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
                showStatus(logsStatus, "Admin CSV downloaded.", false);
            })
            .catch(function (err) {
                showStatus(logsStatus, err.message || "Download failed.", true);
            });
    });
})();
