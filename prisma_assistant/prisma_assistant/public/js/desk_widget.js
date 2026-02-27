// Prisma AI Chat Widget
// Injected into every Frappe desk page via app_include_js in hooks.py
// Supports: Anthropic API, OpenAI API, Gemini API (configured in site settings)

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
		this.render();
		this.bind_events();
	}

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
				<div id="lhdn-chat-input-row">
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

		this.$fab   = $("#lhdn-chat-fab");
		this.$panel = $("#lhdn-chat-panel");
		this.$msgs  = $("#lhdn-chat-messages");
		this.$input = $("#lhdn-chat-input");
		this.$send  = $("#lhdn-chat-send");
	}

	bind_events() {
		this.$fab.on("click", () => this.toggle());
		$("#lhdn-chat-close").on("click", () => this.close());
		$("#lhdn-chat-clear").on("click", () => this.clear());
		this.$send.on("click", () => this.send());

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
			// Place FAB 8px to the left of the edit button's left edge
			const rightOffset = Math.round(window.innerWidth - r.left) + 8;
			this.$fab.css("right", rightOffset + "px");
			this.$panel.css("right", rightOffset + "px");
		} else {
			this.$fab.css("right", "");
			this.$panel.css("right", "");
		}
	}

	toggle() {
		this.is_open ? this.close() : this.open();
	}

	open() {
		this.is_open = true;
		this.$panel.addClass("lhdn-chat-panel--open");
		this.$fab.addClass("lhdn-chat-fab--active");
		this.$input.focus();

		if (this.history.length === 0) {
			this.append_message("assistant",
				__("Hello {0}! I can help with anything in ERPNext — accounting, payroll, inventory, purchasing, HR — as well as Malaysian compliance (PCB, LHDN e-invoicing, EPF, SOCSO) and general coding questions. What do you need?",
				[frappe.session.user_fullname || "there"]));
		}
	}

	close() {
		this.is_open = false;
		this.$panel.removeClass("lhdn-chat-panel--open");
		this.$fab.removeClass("lhdn-chat-fab--active");
	}

	clear() {
		this.history = [];
		this.$msgs.empty();
		this.append_message("assistant",
			__("Conversation cleared. How can I help you?"));
	}

	append_message(role, text) {
		const is_user = role === "user";
		const label = is_user
			? (frappe.session.user_fullname || frappe.session.user)
			: __("Prisma AI");
		const cls = is_user ? "lhdn-msg--user" : "lhdn-msg--assistant";

		// Convert markdown-like line breaks and basic formatting
		const formatted = frappe.utils.escape_html(text)
			.replace(/\n/g, "<br>")
			.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
			.replace(/`([^`]+)`/g, "<code>$1</code>");

		const $msg = $(`
			<div class="lhdn-msg ${cls}">
				<div class="lhdn-msg__label">${label}</div>
				<div class="lhdn-msg__bubble">${formatted}</div>
			</div>
		`);
		this.$msgs.append($msg);
		this.$msgs.scrollTop(this.$msgs[0].scrollHeight);
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

	send() {
		if (this.is_loading) return;

		const text = this.$input.val().trim();
		if (!text) return;

		// Reset input
		this.$input.val("").css("height", "auto");
		this.append_message("user", text);
		this.history.push({ role: "user", content: text });

		// Show typing indicator
		const $typing = this.append_typing();
		this.is_loading = true;
		this.$send.prop("disabled", true);

		frappe.call({
			method: "prisma_assistant.api.chat.send_message",
			args: {
				message: text,
				history: JSON.stringify(this.history.slice(-10)),
			},
			callback: (r) => {
				$typing.remove();
				this.is_loading = false;
				this.$send.prop("disabled", false);

				if (r.message && r.message.reply) {
					const reply = r.message.reply;
					this.history.push({ role: "assistant", content: reply });
					this.append_message("assistant", reply);
				} else if (r.message && r.message.error) {
					this.append_message("assistant",
						`⚠️ ${r.message.error}`);
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
