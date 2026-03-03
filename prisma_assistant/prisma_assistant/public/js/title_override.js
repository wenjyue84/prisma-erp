// Intercept document.title setter — replaces "Desktop" with "Prisma" at the lowest level.
// Runs immediately (no after_ajax needed) so it catches all writes regardless of timing.
(function () {
	var _desc = Object.getOwnPropertyDescriptor(Document.prototype, "title");
	Object.defineProperty(document, "title", {
		get: function () {
			return _desc.get.call(this);
		},
		set: function (v) {
			if (v === "Desktop" || v === "desktop") v = "Prisma";
			_desc.set.call(this, v);
		},
		configurable: true,
	});

	// Fix immediately if already set
	if (document.title === "Desktop") document.title = "Prisma";
})();
