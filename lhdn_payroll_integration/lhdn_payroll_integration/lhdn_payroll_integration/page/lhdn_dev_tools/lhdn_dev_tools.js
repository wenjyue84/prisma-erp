frappe.pages['lhdn-dev-tools'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'LHDN Developer Tools',
        single_column: false
    });
    new LHDNDevTools(page, wrapper);
};

class LHDNDevTools {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.$body = $(wrapper).find('.page-content');
        this._render_layout();
        this._load_system_status();
        this._load_recent_submissions();
    }

    _render_layout() {
        this.$body.html(`
            <div class="container-fluid" style="padding: 16px;">
                <div class="row">
                    <!-- Left column -->
                    <div class="col-md-6">
                        ${this._panel_system_status()}
                        ${this._panel_manual_triggers()}
                        ${this._panel_exemption_tester()}
                    </div>
                    <!-- Right column -->
                    <div class="col-md-6">
                        ${this._panel_connection_test()}
                        ${this._panel_recent_submissions()}
                        ${this._panel_resubmit()}
                        ${this._panel_retrieve_document()}
                    </div>
                </div>
            </div>
        `);
        this._bind_events();
    }

    /* ------------------------------------------------------------------ */
    /* Panel HTML builders                                                  */
    /* ------------------------------------------------------------------ */

    _panel_system_status() {
        return `
        <div class="card mb-3" id="panel-system-status">
            <div class="card-header d-flex justify-content-between align-items-center">
                <strong>1 — System Status</strong>
                <button class="btn btn-xs btn-default btn-refresh-status">Refresh</button>
            </div>
            <div class="card-body p-2">
                <div id="system-status-content">
                    <span class="text-muted">Loading…</span>
                </div>
            </div>
        </div>`;
    }

    _panel_connection_test() {
        return `
        <div class="card mb-3" id="panel-connection-test">
            <div class="card-header"><strong>2 — Connection Test</strong></div>
            <div class="card-body p-2">
                <button class="btn btn-sm btn-primary btn-test-connection">Test Token Endpoint</button>
                <div id="connection-result" class="mt-2"></div>
            </div>
        </div>`;
    }

    _panel_manual_triggers() {
        return `
        <div class="card mb-3" id="panel-manual-triggers">
            <div class="card-header"><strong>3 — Manual Triggers</strong></div>
            <div class="card-body p-2">
                <div class="btn-group-vertical w-100">
                    <button class="btn btn-sm btn-default btn-run-poller mb-1">Run Status Poller</button>
                    <button class="btn btn-sm btn-default btn-run-consolidation mb-1">Run Monthly Consolidation</button>
                    <button class="btn btn-sm btn-default btn-run-retention">Run Yearly Retention</button>
                </div>
                <pre id="trigger-output" class="mt-2 p-2 bg-light" style="font-size:12px;max-height:120px;overflow:auto;display:none;"></pre>
            </div>
        </div>`;
    }

    _panel_exemption_tester() {
        return `
        <div class="card mb-3" id="panel-exemption-tester">
            <div class="card-header"><strong>4 — Exemption Tester</strong></div>
            <div class="card-body p-2">
                <div class="form-group">
                    <label class="control-label">Employee</label>
                    <input type="text" class="form-control form-control-sm input-exemption-employee"
                           placeholder="Employee ID (e.g. EMP-0001)">
                </div>
                <div class="form-group">
                    <label class="control-label">Salary Slip <small class="text-muted">(optional)</small></label>
                    <input type="text" class="form-control form-control-sm input-exemption-slip"
                           placeholder="Salary Slip name (optional)">
                </div>
                <button class="btn btn-sm btn-primary btn-check-exemption">Check Exemption</button>
                <div id="exemption-result" class="mt-2"></div>
            </div>
        </div>`;
    }

    _panel_recent_submissions() {
        return `
        <div class="card mb-3" id="panel-recent-submissions">
            <div class="card-header d-flex justify-content-between align-items-center">
                <strong>5 — Recent Submissions</strong>
                <div class="d-flex align-items-center">
                    <select class="form-control form-control-sm select-status-filter" style="width:120px;margin-right:6px;">
                        <option value="">All</option>
                        <option value="Pending">Pending</option>
                        <option value="Submitted">Submitted</option>
                        <option value="Valid">Valid</option>
                        <option value="Invalid">Invalid</option>
                        <option value="Exempt">Exempt</option>
                        <option value="Cancelled">Cancelled</option>
                    </select>
                    <button class="btn btn-xs btn-default btn-refresh-submissions">Refresh</button>
                </div>
            </div>
            <div class="card-body p-2">
                <div id="submissions-content">
                    <span class="text-muted">Loading…</span>
                </div>
            </div>
        </div>`;
    }

    _panel_resubmit() {
        return `
        <div class="card mb-3" id="panel-resubmit">
            <div class="card-header"><strong>6 — Re-submit to LHDN</strong></div>
            <div class="card-body p-2">
                <div class="form-group">
                    <label class="control-label">DocType</label>
                    <select class="form-control form-control-sm select-resubmit-doctype">
                        <option value="Salary Slip">Salary Slip</option>
                        <option value="Expense Claim">Expense Claim</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="control-label">Document Name</label>
                    <input type="text" class="form-control form-control-sm input-resubmit-docname"
                           placeholder="e.g. Sal Slip/2026/00001">
                </div>
                <button class="btn btn-sm btn-warning btn-resubmit">Re-submit</button>
                <div id="resubmit-result" class="mt-2"></div>
            </div>
        </div>`;
    }

    _panel_retrieve_document() {
        return `
        <div class="card mb-3" id="panel-retrieve-document">
            <div class="card-header"><strong>7 — Retrieve from LHDN</strong></div>
            <div class="card-body p-2">
                <p class="text-muted" style="font-size:12px;">
                    Fetches the validated XML stored on the LHDN portal via
                    <code>GET /api/v1.0/documents/{uuid}/raw</code> and saves it
                    to the document's <em>LHDN Raw Document</em> field for audit comparison.
                </p>
                <div class="form-group">
                    <label class="control-label">DocType</label>
                    <select class="form-control form-control-sm select-retrieve-doctype">
                        <option value="Salary Slip">Salary Slip</option>
                        <option value="Expense Claim">Expense Claim</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="control-label">Document Name</label>
                    <input type="text" class="form-control form-control-sm input-retrieve-docname"
                           placeholder="e.g. Sal Slip/2026/00001">
                </div>
                <button class="btn btn-sm btn-info btn-retrieve-document">Retrieve from LHDN</button>
                <div id="retrieve-result" class="mt-2"></div>
            </div>
        </div>`;
    }

    /* ------------------------------------------------------------------ */
    /* Event binding                                                        */
    /* ------------------------------------------------------------------ */

    _bind_events() {
        const $b = this.$body;

        $b.find('.btn-refresh-status').on('click', () => this._load_system_status());

        $b.find('.btn-test-connection').on('click', () => this._test_connection());

        $b.find('.btn-run-poller').on('click', () =>
            this._run_trigger('lhdn_dev_tools.run_status_poller', 'Status Poller'));

        $b.find('.btn-run-consolidation').on('click', () =>
            this._run_trigger('lhdn_dev_tools.run_monthly_consolidation', 'Monthly Consolidation'));

        $b.find('.btn-run-retention').on('click', () =>
            this._run_trigger('lhdn_dev_tools.run_yearly_retention', 'Yearly Retention'));

        $b.find('.btn-check-exemption').on('click', () => this._check_exemption());

        $b.find('.btn-refresh-submissions').on('click', () => this._load_recent_submissions());
        $b.find('.select-status-filter').on('change', () => this._load_recent_submissions());

        $b.find('.btn-resubmit').on('click', () => this._resubmit());

        $b.find('.btn-retrieve-document').on('click', () => this._retrieve_document());
    }

    /* ------------------------------------------------------------------ */
    /* Panel 1 — System Status                                              */
    /* ------------------------------------------------------------------ */

    _load_system_status() {
        const $el = this.$body.find('#system-status-content');
        $el.html('<span class="text-muted">Loading…</span>');

        frappe.call({
            method: 'lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.get_system_status',
            callback: (r) => {
                if (r.exc) { $el.html(`<span class="text-danger">${r.exc}</span>`); return; }
                const d = r.message;
                if (d.error) { $el.html(`<span class="text-danger">${d.error}</span>`); return; }
                $el.html(this._status_table(d));
            }
        });
    }

    _status_table(d) {
        const badge = (ok) => ok
            ? '<span class="badge badge-success">OK</span>'
            : '<span class="badge badge-danger">Missing</span>';
        const rows = [
            ['Company', d.company],
            ['TIN', d.company_tin || '<em class="text-muted">not set</em>'],
            ['Client ID', badge(d.client_id_set)],
            ['Sandbox URL', d.sandbox_url || '<em class="text-muted">not set</em>'],
            ['Integration Type', d.integration_type || '<em class="text-muted">not set</em>'],
            ['Scheduler Last Sync', d.scheduler_last_sync],
            ['Queue Depth (Pending)', d.queue_depth],
        ];
        const trs = rows.map(([k, v]) =>
            `<tr><td class="text-muted" style="width:50%;padding:3px 6px;">${k}</td><td style="padding:3px 6px;">${v}</td></tr>`
        ).join('');
        return `<table class="table table-condensed table-bordered" style="margin-bottom:0;font-size:12px;">${trs}</table>`;
    }

    /* ------------------------------------------------------------------ */
    /* Panel 2 — Connection Test                                            */
    /* ------------------------------------------------------------------ */

    _test_connection() {
        const $el = this.$body.find('#connection-result');
        $el.html('<span class="text-muted">Testing…</span>');

        frappe.call({
            method: 'lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.test_lhdn_connection',
            callback: (r) => {
                if (r.exc) { $el.html(`<span class="text-danger">${r.exc}</span>`); return; }
                const d = r.message;
                const statusColor = d.http_status === 200 ? 'success'
                    : d.http_status ? 'warning' : 'danger';
                const statusLabel = d.http_status
                    ? `HTTP ${d.http_status}`
                    : 'No response';
                let html = `<span class="badge badge-${statusColor}">${statusLabel}</span>`;
                if (d.elapsed_ms !== null && d.elapsed_ms !== undefined) {
                    html += ` <span class="text-muted">${d.elapsed_ms} ms</span>`;
                }
                if (d.error_detail) {
                    html += `<br><small class="text-danger">${frappe.utils.escape_html(d.error_detail)}</small>`;
                }
                $el.html(html);
            }
        });
    }

    /* ------------------------------------------------------------------ */
    /* Panel 3 — Manual Triggers                                            */
    /* ------------------------------------------------------------------ */

    _run_trigger(method, label) {
        const $out = this.$body.find('#trigger-output');
        $out.show().text(`Running ${label}…`);

        frappe.call({
            method: `lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.${method.split('.').pop()}`,
            callback: (r) => {
                if (r.exc) { $out.text(r.exc); return; }
                const d = r.message;
                const icon = d.success ? '✓' : '✗';
                $out.text(`[${label}] ${icon} ${d.output}`);
            }
        });
    }

    /* ------------------------------------------------------------------ */
    /* Panel 4 — Exemption Tester                                           */
    /* ------------------------------------------------------------------ */

    _check_exemption() {
        const employee = this.$body.find('.input-exemption-employee').val().trim();
        const salary_slip = this.$body.find('.input-exemption-slip').val().trim();
        const $el = this.$body.find('#exemption-result');

        if (!employee) {
            frappe.msgprint('Please enter an Employee ID.');
            return;
        }

        $el.html('<span class="text-muted">Checking…</span>');

        frappe.call({
            method: 'lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.check_exemption',
            args: { employee, salary_slip: salary_slip || null },
            callback: (r) => {
                if (r.exc) { $el.html(`<span class="text-danger">${r.exc}</span>`); return; }
                const d = r.message;
                const badge = d.in_scope
                    ? '<span class="badge badge-success">In Scope</span>'
                    : '<span class="badge badge-secondary">Exempt</span>';
                $el.html(`${badge} <small>${frappe.utils.escape_html(d.reason)}</small>`);
            }
        });
    }

    /* ------------------------------------------------------------------ */
    /* Panel 5 — Recent Submissions                                         */
    /* ------------------------------------------------------------------ */

    _load_recent_submissions() {
        const status_filter = this.$body.find('.select-status-filter').val();
        const $el = this.$body.find('#submissions-content');
        $el.html('<span class="text-muted">Loading…</span>');

        frappe.call({
            method: 'lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.get_recent_submissions',
            args: { status_filter: status_filter || null },
            callback: (r) => {
                if (r.exc) { $el.html(`<span class="text-danger">${r.exc}</span>`); return; }
                const rows = r.message || [];
                if (!rows.length) {
                    $el.html('<span class="text-muted">No submissions found.</span>');
                    return;
                }
                $el.html(this._submissions_table(rows));
            }
        });
    }

    _submissions_table(rows) {
        const STATUS_COLOR = {
            Valid: 'success', Pending: 'warning', Invalid: 'danger',
            Exempt: 'secondary', Submitted: 'info', Cancelled: 'secondary'
        };
        const trs = rows.map(row => {
            const color = STATUS_COLOR[row.custom_lhdn_status] || 'secondary';
            const badge = `<span class="badge badge-${color}">${row.custom_lhdn_status || '—'}</span>`;
            const uuid = row.custom_lhdn_uuid
                ? `<small class="text-muted">${row.custom_lhdn_uuid.substring(0, 8)}…</small>`
                : '—';
            return `<tr>
                <td style="font-size:11px;">${row.doctype}</td>
                <td style="font-size:11px;">${row.name}</td>
                <td style="font-size:11px;">${row.employee || '—'}</td>
                <td style="font-size:11px;">${row.posting_date || '—'}</td>
                <td style="font-size:11px;">${badge}</td>
                <td style="font-size:11px;">${uuid}</td>
            </tr>`;
        }).join('');
        return `
        <div style="overflow-x:auto;">
        <table class="table table-condensed table-bordered" style="font-size:11px;margin-bottom:0;">
            <thead><tr>
                <th>DocType</th><th>Name</th><th>Employee</th>
                <th>Date</th><th>Status</th><th>UUID</th>
            </tr></thead>
            <tbody>${trs}</tbody>
        </table>
        </div>`;
    }

    /* ------------------------------------------------------------------ */
    /* Panel 6 — Re-submit                                                  */
    /* ------------------------------------------------------------------ */

    _resubmit() {
        const doctype = this.$body.find('.select-resubmit-doctype').val();
        const docname = this.$body.find('.input-resubmit-docname').val().trim();
        const $el = this.$body.find('#resubmit-result');

        if (!docname) {
            frappe.msgprint('Please enter a Document Name.');
            return;
        }

        frappe.confirm(
            `Re-submit <b>${frappe.utils.escape_html(docname)}</b> (${doctype}) to LHDN?`,
            () => {
                $el.html('<span class="text-muted">Re-submitting…</span>');
                frappe.call({
                    method: 'lhdn_payroll_integration.services.submission_service.resubmit_to_lhdn',
                    args: { docname, doctype },
                    callback: (r) => {
                        if (r.exc) {
                            $el.html(`<span class="text-danger">${frappe.utils.escape_html(r.exc)}</span>`);
                            return;
                        }
                        $el.html('<span class="badge badge-success">Queued for re-submission</span>');
                        // Refresh submissions table to show Pending status
                        this._load_recent_submissions();
                    }
                });
            }
        );
    }

    /* ------------------------------------------------------------------ */
    /* Panel 7 — Retrieve from LHDN                                         */
    /* ------------------------------------------------------------------ */

    _retrieve_document() {
        const doctype = this.$body.find('.select-retrieve-doctype').val();
        const docname = this.$body.find('.input-retrieve-docname').val().trim();
        const $el = this.$body.find('#retrieve-result');

        if (!docname) {
            frappe.msgprint('Please enter a Document Name.');
            return;
        }

        $el.html('<span class="text-muted">Retrieving from LHDN portal…</span>');

        frappe.call({
            method: 'lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.retrieve_lhdn_document',
            args: { docname, doctype },
            callback: (r) => {
                if (r.exc) {
                    $el.html(`<span class="text-danger">${frappe.utils.escape_html(r.exc)}</span>`);
                    return;
                }
                const d = r.message;
                if (d.success) {
                    const preview = d.raw_xml
                        ? frappe.utils.escape_html(d.raw_xml.substring(0, 200)) + (d.raw_xml.length > 200 ? '…' : '')
                        : '(empty)';
                    $el.html(`
                        <span class="badge badge-success">Retrieved & Saved</span>
                        <pre class="mt-2 p-2 bg-light" style="font-size:11px;max-height:100px;overflow:auto;">${preview}</pre>
                    `);
                } else {
                    $el.html(`<span class="badge badge-danger">Failed</span>
                        <small class="text-danger ml-1">${frappe.utils.escape_html(d.error_detail || '')}</small>`);
                }
            }
        });
    }
}
