// Prisma AI Chat Widget
// Injected into every Frappe desk page via app_include_js in hooks.py
// Supports: Anthropic API, OpenAI API, Gemini API (configured in site settings)
// Features: copy button, markdown rendering, persistent history, context injection, file attachments

frappe.provide("prisma_assistant.chat");

$(document).on("app_ready", function () {
	prisma_assistant.chat.widget = new PrismaAIChatWidget();
	prisma_assistant.chat.widget.init();
});

class PrismaAIChatWidget {
	init() {
		this.history = [];
		this.is_open = false;
		this.is_loading = false;
		this.pendingFile = null;
		this.render();
		this.bind_events();
		this._load_history();
		this._setup_context_chip();
	}

	// ── Storage key (per user) ────────────────────────────────────────────────

	get _storageKey() {
		return "prisma_ai_history_" + (frappe.session.user || "guest");
	}

	// ── Render HTML ───────────────────────────────────────────────────────────

	render() {
		const html = `
			<div id="lhdn-chat-fab" title="${__("Prisma AI")}">
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none"
				     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
				</svg>
			</div>
			<div id="lhdn-chat-panel">
				<div id="lhdn-chat-header">
					<div id="lhdn-chat-header-info">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
						     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
						</svg>
						<span>${__("Prisma AI")}</span>
					</div>
					<div id="lhdn-chat-header-actions">
						<button id="lhdn-chat-newchat" title="${__("New Chat")}">
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none"
							     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M12 5v14M5 12h14"/>
							</svg>
						</button>
						<button id="lhdn-chat-clear" title="${__("Clear conversation")}">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
							     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
								<path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
							</svg>
						</button>
						<button id="lhdn-chat-close" title="${__("Close")}">&#x2715;</button>
					</div>
				</div>
				<div id="lhdn-chat-messages"></div>
				<div id="lhdn-context-chip-row"></div>
				<div id="lhdn-file-preview-row"></div>
				<div id="lhdn-chat-input-row">
					<input type="file" id="lhdn-file-input"
					       accept="image/jpeg,image/png,image/webp,image/gif,application/pdf"
					       style="display:none">
					<button id="lhdn-attach-btn" title="${__("Attach image or PDF")}">
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
						     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
						</svg>
					</button>
					<textarea id="lhdn-chat-input" rows="1"
					          placeholder="${__("Ask anything about ERPNext, payroll, LHDN...")}"></textarea>
					<button id="lhdn-chat-send" title="${__("Send (Enter)")}">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
						     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<line x1="22" y1="2" x2="11" y2="13"/>
							<polygon points="22 2 15 22 11 13 2 9 22 2"/>
						</svg>
					</button>
				</div>
				<div id="lhdn-chat-footer">
					${__("Powered by Prisma Technology Solution Sdn Bhd")} &mdash;
					<a href="/app/prisma-ai-settings" target="_blank">${__("Settings")}</a>
				</div>
			</div>
		`;
		$("body").append(html);

		this.$fab            = $("#lhdn-chat-fab");
		this.$panel          = $("#lhdn-chat-panel");
		this.$msgs           = $("#lhdn-chat-messages");
		this.$input          = $("#lhdn-chat-input");
		this.$send           = $("#lhdn-chat-send");
		this.$fileInput      = $("#lhdn-file-input");
		this.$attachBtn      = $("#lhdn-attach-btn");
		this.$filePreviewRow = $("#lhdn-file-preview-row");
		this.$contextChipRow = $("#lhdn-context-chip-row");
	}

	// ── Events ────────────────────────────────────────────────────────────────

	bind_events() {
		this.$fab.on("click", () => this.toggle());
		$("#lhdn-chat-close").on("click", () => this.close());
		$("#lhdn-chat-clear").on("click", () => this.clear());
		$("#lhdn-chat-newchat").on("click", () => this.new_chat());
		this.$send.on("click", () => this.send());

		// File attach
		this.$attachBtn.on("click", () => this.$fileInput[0].click());
		this.$fileInput.on("change", (e) => this._on_file_selected(e));

		// Send on Enter (Shift+Enter = newline)
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});

		// Auto-resize textarea
		this.$input.on("input", () => {
			this.$input[0].style.height = "auto";
			this.$input[0].style.height = Math.min(this.$input[0].scrollHeight, 120) + "px";
		});

		// Avoid overlap with ERPNext desktop-edit button (workspace pages)
		$(document).on("page-change", () => this._adjust_position());
		setTimeout(() => this._adjust_position(), 300);
	}

	_adjust_position() {
		const editBtn = document.querySelector(".desktop-edit");
		if (editBtn) {
			const r = editBtn.getBoundingClientRect();
			const rightOffset = Math.round(window.innerWidth - r.left) + 8;
			this.$fab.css("right", rightOffset + "px");
			this.$panel.css("right", rightOffset + "px");
		} else {
			this.$fab.css("right", "");
			this.$panel.css("right", "");
		}
	}

	// ── History persistence (US-PA-03) ────────────────────────────────────────

	_load_history() {
		try {
			const saved = JSON.parse(localStorage.getItem(this._storageKey) || "[]");
			if (Array.isArray(saved) && saved.length > 0) {
				this.history = saved;
				saved.forEach(m => this.append_message(m.role, m.content, true));
			}
		} catch (e) {
			this.history = [];
		}
	}

	_save_history() {
		try {
			localStorage.setItem(this._storageKey, JSON.stringify(this.history.slice(-50)));
		} catch (e) {
			// localStorage unavailable — silent fallback
		}
	}

	_clear_storage() {
		try {
			localStorage.removeItem(this._storageKey);
		} catch (e) {}
	}

	// ── Context chip (US-PA-04) ───────────────────────────────────────────────

	_setup_context_chip() {
		const $chip = $(`<div class="pa-context-chip" style="display:none"></div>`);
		this.$contextChipRow.append($chip);
		this.$contextChip = $chip;

		$chip.on("click", () => this._inject_context());

		// Route change listeners
		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", () => this._update_context_chip());
		}
		$(document).on("page-change", () => this._update_context_chip());
		setTimeout(() => this._update_context_chip(), 600);
	}

	_update_context_chip() {
		if (window.innerWidth < 480) {
			this.$contextChip.hide();
			return;
		}
		const route = frappe.get_route ? frappe.get_route() : [];
		if (route[0] === "Form" && route[1] && route[2]) {
			this.$contextChip.text("📋 Add " + route[1] + " context").show();
		} else {
			this.$contextChip.hide();
		}
	}

	_inject_context() {
		const route = frappe.get_route ? frappe.get_route() : [];
		if (route[0] !== "Form" || !route[1] || !route[2]) return;

		const doctype = route[1];
		const docname = route[2];
		const doc = frappe.get_doc(doctype, docname);
		if (!doc) {
			frappe.show_alert({ message: __("Document not loaded yet"), indicator: "orange" });
			return;
		}

		const lines = Object.entries(doc)
			.filter(([k, v]) =>
				!k.startsWith("__") &&
				v !== null && v !== "" && v !== 0 &&
				typeof v !== "object" && typeof v !== "function"
			)
			.map(([k, v]) => `${k}: ${v}`)
			.join("\n");

		const prefix = `[Document Context: ${doctype} "${docname}"]\n${lines}\n\n`;
		const ta = this.$input[0];
		ta.value = prefix + ta.value;
		ta.dispatchEvent(new Event("input"));
		ta.focus();
	}

	// ── File attachment (US-PA-05) ────────────────────────────────────────────

	_on_file_selected(e) {
		const file = e.target.files[0];
		if (!file) return;

		const isPDF = file.type === "application/pdf";
		const maxSize = isPDF ? 10 * 1024 * 1024 : 5 * 1024 * 1024;

		if (file.size > maxSize) {
			frappe.msgprint({
				message: __("File too large. Maximum size: {0}", [isPDF ? "10 MB" : "5 MB"]),
				indicator: "red",
			});
			this.$fileInput.val("");
			return;
		}

		const reader = new FileReader();
		reader.onload = (ev) => {
			const dataUrl = ev.target.result;
			const b64 = dataUrl.split(",")[1];
			this.pendingFile = { name: file.name, type: file.type, data: b64 };
			this._show_file_preview(file, dataUrl);
		};
		reader.readAsDataURL(file);
		// Reset so same file can be re-selected
		this.$fileInput.val("");
	}

	_show_file_preview(file, dataUrl) {
		this.$filePreviewRow.empty();
		const isPDF = file.type === "application/pdf";
		const previewContent = isPDF
			? `<span class="pa-file-icon">📄</span><span class="pa-file-name">${frappe.utils.escape_html(file.name)}</span>`
			: `<img src="${dataUrl}" class="pa-file-thumb" alt="${frappe.utils.escape_html(file.name)}">`;

		const $preview = $(`
			<div class="pa-file-preview">
				${previewContent}
				<button class="pa-file-remove" title="${__("Remove attachment")}">&#x2715;</button>
			</div>
		`);
		$preview.find(".pa-file-remove").on("click", () => {
			this.pendingFile = null;
			this.$filePreviewRow.empty();
		});
		this.$filePreviewRow.append($preview);
	}

	// ── Markdown renderer (US-PA-02) ──────────────────────────────────────────

	_markdownToHtml(text) {
		// Step 1: Escape HTML (XSS prevention)
		let t = text
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;");

		// Step 2: Extract fenced code blocks into placeholders
		const codeBlocks = [];
		t = t.replace(/```(?:[a-z]*\n?)?([\s\S]*?)```/g, (_, code) => {
			const idx = codeBlocks.length;
			codeBlocks.push(`<pre><code>${code.replace(/^\n|\n$/g, "")}</code></pre>`);
			return `\x00CODE${idx}\x00`;
		});

		// Step 3: Inline code
		t = t.replace(/`([^`\n]+)`/g, "<code>$1</code>");

		// Step 4: Headers (# to ######)
		t = t.replace(/^(#{1,6})\s+(.+)$/gm, (_, hashes, content) =>
			`<h${hashes.length}>${content}</h${hashes.length}>`
		);

		// Step 5: Bold + italic
		t = t.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");

		// Step 6: Bold
		t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

		// Step 7: Italic
		t = t.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

		// Step 8: Horizontal rule
		t = t.replace(/^---$/gm, "<hr>");

		// Step 9: Unordered lists (consecutive lines starting with - or *)
		t = t.replace(/((?:^[ \t]*[-*]\s+.+$\n?)+)/gm, (block) => {
			const items = block.trim().split("\n")
				.map(line => `<li>${line.replace(/^[ \t]*[-*]\s+/, "")}</li>`)
				.join("");
			return `<ul>${items}</ul>`;
		});

		// Step 10: Ordered lists (consecutive lines starting with N.)
		t = t.replace(/((?:^[ \t]*\d+\.\s+.+$\n?)+)/gm, (block) => {
			const items = block.trim().split("\n")
				.map(line => `<li>${line.replace(/^[ \t]*\d+\.\s+/, "")}</li>`)
				.join("");
			return `<ol>${items}</ol>`;
		});

		// Step 11: Paragraph breaks
		const parts = t.split("\n\n");
		const wrapped = parts.map(part => {
			const trimmed = part.trim();
			// Don't wrap block-level elements in <p>
			if (/^<(?:ul|ol|h[1-6]|hr|pre|\x00CODE)/.test(trimmed)) return trimmed;
			if (!trimmed) return "";
			return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
		});
		t = wrapped.filter(Boolean).join("\n");

		// Restore fenced code blocks
		codeBlocks.forEach((block, idx) => {
			t = t.replace(`\x00CODE${idx}\x00`, block);
		});

		return t;
	}

	// ── Widget state ──────────────────────────────────────────────────────────

	toggle() {
		this.is_open ? this.close() : this.open();
	}

	open() {
		this.is_open = true;
		this.$panel.addClass("lhdn-chat-panel--open");
		this.$fab.addClass("lhdn-chat-fab--active");
		this.$input.focus();

		if (this.history.length === 0) {
			this._render_greeting();
		}
		this._update_context_chip();
	}

	close() {
		this.is_open = false;
		this.$panel.removeClass("lhdn-chat-panel--open");
		this.$fab.removeClass("lhdn-chat-fab--active");
	}

	_render_greeting() {
		this.append_message("assistant",
			__("Hello {0}! I can help with anything in ERPNext — accounting, payroll, inventory, purchasing, HR — as well as Malaysian compliance (PCB, LHDN e-invoicing, EPF, SOCSO) and general coding questions. What do you need?",
			[frappe.session.user_fullname || "there"]),
			true  // skipSave: greeting is UI-only, not stored in history
		);
	}

	clear() {
		this.history = [];
		this._clear_storage();
		this.$msgs.empty();
		this.append_message("assistant", __("Conversation cleared. How can I help you?"), true);
	}

	new_chat() {
		this.history = [];
		this._clear_storage();
		this.$msgs.empty();
		this.pendingFile = null;
		this.$filePreviewRow.empty();
		this._render_greeting();
	}

	// ── Message rendering ─────────────────────────────────────────────────────

	/**
	 * Render a message bubble.
	 * @param {string} role - "user" or "assistant"
	 * @param {string} text - Plain text content
	 * @param {boolean} skipSave - true when replaying from localStorage (avoids re-push)
	 */
	append_message(role, text, skipSave = false) {
		const is_user = role === "user";
		const label = is_user
			? (frappe.session.user_fullname || frappe.session.user)
			: __("Prisma AI");
		const cls = is_user ? "lhdn-msg--user" : "lhdn-msg--assistant";

		let $msg;

		if (!is_user) {
			// Assistant messages: full markdown + copy button (US-PA-01 + US-PA-02)
			const contentHtml = this._markdownToHtml(text);
			const rawEscaped = text
				.replace(/&/g, "&amp;")
				.replace(/"/g, "&quot;");

			$msg = $(`
				<div class="lhdn-msg ${cls}">
					<div class="lhdn-msg__label">${label}</div>
					<div class="pa-msg-wrapper">
						<div class="lhdn-msg__bubble pa-msg-content">${contentHtml}</div>
						<button class="pa-copy-btn" title="${__("Copy")}" data-raw="${rawEscaped}">⧉</button>
					</div>
				</div>
			`);

			$msg.find(".pa-copy-btn").on("click", function () {
				const raw = this.dataset.raw
					.replace(/&amp;/g, "&")
					.replace(/&quot;/g, '"');
				navigator.clipboard.writeText(raw).then(() => {
					this.textContent = "✓";
					setTimeout(() => { this.textContent = "⧉"; }, 1500);
				}).catch(() => {
					frappe.show_alert({ message: __("Copy failed"), indicator: "red" });
				});
			});
		} else {
			// User messages: plain text (escaping only, no markdown)
			const contentHtml = frappe.utils.escape_html(text).replace(/\n/g, "<br>");
			$msg = $(`
				<div class="lhdn-msg ${cls}">
					<div class="lhdn-msg__label">${label}</div>
					<div class="lhdn-msg__bubble">${contentHtml}</div>
				</div>
			`);
		}

		this.$msgs.append($msg);
		this.$msgs.scrollTop(this.$msgs[0].scrollHeight);

		// Persist to history (unless replaying from localStorage)
		if (!skipSave) {
			this.history.push({ role, content: text });
			this._save_history();
		}

		return $msg;
	}

	append_typing() {
		const $typing = $(`
			<div class="lhdn-msg lhdn-msg--assistant lhdn-msg--typing">
				<div class="lhdn-msg__label">${__("Prisma AI")}</div>
				<div class="lhdn-msg__bubble">
					<span class="lhdn-dot"></span>
					<span class="lhdn-dot"></span>
					<span class="lhdn-dot"></span>
				</div>
			</div>
		`);
		this.$msgs.append($typing);
		this.$msgs.scrollTop(this.$msgs[0].scrollHeight);
		return $typing;
	}

	// ── Send ──────────────────────────────────────────────────────────────────

	send() {
		if (this.is_loading) return;

		const text = this.$input.val().trim();
		if (!text && !this.pendingFile) return;

		const msgText = text || `[Attached: ${this.pendingFile.name}]`;

		// Reset input
		this.$input.val("").css("height", "auto");

		// Render user message — this also pushes to this.history
		this.append_message("user", msgText);

		// Build API args: pass history WITHOUT the message we just pushed
		// (server appends current message itself via send_message(message=...) param)
		const historyForApi = this.history.slice(0, -1).slice(-10);
		const args = {
			message: msgText,
			history: JSON.stringify(historyForApi),
		};

		// Attach file if pending (US-PA-05 / US-PA-06)
		if (this.pendingFile) {
			args.files = JSON.stringify([this.pendingFile]);
		}

		// Clear pending file state
		this.pendingFile = null;
		this.$filePreviewRow.empty();

		// Show typing indicator
		const $typing = this.append_typing();
		this.is_loading = true;
		this.$send.prop("disabled", true);

		frappe.call({
			method: "prisma_assistant.api.chat.send_message",
			args,
			callback: (r) => {
				$typing.remove();
				this.is_loading = false;
				this.$send.prop("disabled", false);

				if (r.message && r.message.reply) {
					const reply = r.message.reply;
					this.append_message("assistant", reply);
				} else if (r.message && r.message.error) {
					this.append_message("assistant", `⚠️ ${r.message.error}`);
				} else {
					this.append_message("assistant",
						__("Sorry, I encountered an error. Please try again."));
				}
			},
			error: (r) => {
				$typing.remove();
				this.is_loading = false;
				this.$send.prop("disabled", false);

				const msg = r && r.responseJSON && r.responseJSON._error_message
					? r.responseJSON._error_message
					: __("Connection error. Please check your network.");
				this.append_message("assistant", `⚠️ ${msg}`);
			},
		});
	}
}
