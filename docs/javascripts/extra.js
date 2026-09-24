(() => {
  const shellCommands = new Set([
    "age", "ansible", "ansible-playbook", "apt", "apt-get", "awk", "cat",
    "cd", "chmod", "chown", "cp", "curl", "dig", "docker", "docker-compose",
    "echo", "export", "find", "gh", "git", "grep", "gzip", "host", "jq",
    "journalctl", "make", "mkdir", "mv", "nslookup", "openssl", "pg_dump",
    "pg_restore", "pip", "pip3", "printf", "psql", "python", "python3", "read",
    "restic", "rm", "rsync", "scp", "sed", "set", "sleep", "sops", "source",
    "ssh", "ssh-keygen", "sudo", "systemctl", "tar", "tee", "test", "ufw",
    "unzip", "wget", "yq", "zsh"
  ]);

  const shellSelector = [
    ".highlight.language-bash code",
    ".highlight.language-sh code",
    ".highlight.language-shell code",
    ".highlight.language-zsh code",
    "code.language-bash",
    "code.language-sh",
    "code.language-shell",
    "code.language-zsh"
  ].join(",");

  const enhanceShellTextNode = (node) => {
    const parent = node.parentElement;
    if (!parent || !node.nodeValue || !node.nodeValue.trim()) return;

    // Preserve tokens that Pygments already classified. Plain Text tokens are
    // left as bare text (or inside line-id spans without a class), which is the
    // part we enrich here.
    if (parent.matches("span[class]")) return;

    const parts = node.nodeValue.split(/(\s+|&&|\|\||[;|])/g);
    let changed = false;
    const fragment = document.createDocumentFragment();

    for (const part of parts) {
      if (!part) continue;
      const bare = part.replace(/^[('"`]+|[)'"`,]+$/g, "");
      let className = "";

      if (shellCommands.has(bare)) {
        className = "solo-shell-command";
      } else if (/^--?[A-Za-z0-9][A-Za-z0-9_-]*$/.test(bare)) {
        className = "solo-shell-option";
      }

      if (!className) {
        fragment.appendChild(document.createTextNode(part));
        continue;
      }

      changed = true;
      const start = part.indexOf(bare);
      if (start > 0) fragment.appendChild(document.createTextNode(part.slice(0, start)));
      const span = document.createElement("span");
      span.className = className;
      span.textContent = bare;
      fragment.appendChild(span);
      const end = start + bare.length;
      if (end < part.length) fragment.appendChild(document.createTextNode(part.slice(end)));
    }

    if (changed) node.replaceWith(fragment);
  };

  const enhanceShellBlocks = () => {
    document.querySelectorAll(shellSelector).forEach((code) => {
      if (code.dataset.soloShellEnhanced === "true") return;
      const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(enhanceShellTextNode);
      code.dataset.soloShellEnhanced = "true";
    });
  };

  const copyIcon = `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="8" y="8" width="11" height="11" rx="2"></rect>
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
    </svg>`;

  const checkIcon = `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m5 12 4 4L19 6"></path>
    </svg>`;

  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    textarea.remove();
    if (!ok) throw new Error("copy command failed");
  };

  const setupCopyButtons = () => {
    const isRussian = document.documentElement.lang.toLowerCase().startsWith("ru");
    const copyLabel = isRussian ? "Копировать в буфер" : "Copy to clipboard";
    const copiedLabel = isRussian ? "Скопировано" : "Copied";

    document.querySelectorAll(".md-typeset .highlight").forEach((block) => {
      // Material may have rendered its own button from an older cached page;
      // remove it so only the deterministic Solo VPS control is visible.
      block.querySelectorAll(".md-clipboard").forEach((button) => button.remove());
      if (block.dataset.soloCopyReady === "true") return;
      if (block.classList.contains("no-copy") || block.querySelector("code.no-copy")) return;

      const code = block.querySelector("pre > code");
      if (!code) return;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "solo-copy-button";
      button.setAttribute("aria-label", copyLabel);
      button.title = copyLabel;
      button.innerHTML = copyIcon;

      button.addEventListener("click", async () => {
        try {
          // Copy source whitespace, not layout-derived line breaks from the
          // syntax highlighter's line spans (innerText can add blank lines).
          await copyText(code.textContent.replace(/\n$/, ""));
          button.dataset.copied = "true";
          button.setAttribute("aria-label", copiedLabel);
          button.title = copiedLabel;
          button.innerHTML = checkIcon;
          window.setTimeout(() => {
            button.dataset.copied = "false";
            button.setAttribute("aria-label", copyLabel);
            button.title = copyLabel;
            button.innerHTML = copyIcon;
          }, 1400);
        } catch (error) {
          console.error("Solo VPS: could not copy code block", error);
        }
      });

      block.appendChild(button);
      block.dataset.soloCopyReady = "true";
    });
  };

  const setupTocSync = () => {
    const sidebar = document.querySelector(".md-sidebar--secondary");
    if (!sidebar || sidebar.dataset.soloTocSync === "true") return;

    const links = Array.from(
      sidebar.querySelectorAll('a.md-nav__link[href^="#"]')
    );
    const entries = links
      .map((link) => {
        const hash = link.hash || link.getAttribute("href") || "";
        if (!hash.startsWith("#") || hash.length < 2) return null;
        let id;
        try {
          id = decodeURIComponent(hash.slice(1));
        } catch {
          id = hash.slice(1);
        }
        const target = document.getElementById(id);
        return target ? { link, target, hash, id } : null;
      })
      .filter(Boolean);

    if (!entries.length) return;

    sidebar.dataset.soloTocSync = "true";
    document.body.classList.add("solo-toc-sync");

    const setActive = (activeLink) => {
      for (const { link } of entries) {
        link.classList.toggle("solo-toc-active", link === activeLink);
      }
    };

    const linkForHash = (hash) => {
      if (!hash) return null;
      let id = hash.replace(/^#/, "");
      try {
        id = decodeURIComponent(id);
      } catch {
        // Keep the raw id if it isn't valid percent-encoding.
      }
      return entries.find(({ id: candidate }) => candidate === id)?.link || null;
    };

    let clickLockUntil = 0;
    let frame = 0;

    const updateFromScroll = () => {
      frame = 0;
      if (performance.now() < clickLockUntil) return;

      const header = document.querySelector(".md-header");
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      // Sample a little below the fixed header. This avoids the strict-boundary
      // lag of Material's native scroll-spy when an anchor lands exactly on its
      // activation threshold.
      const activationLine = headerHeight + 48;
      let activeLink = null;

      for (const { link, target } of entries) {
        if (target.getBoundingClientRect().top <= activationLine) {
          activeLink = link;
        } else {
          break;
        }
      }
      setActive(activeLink);
    };

    const scheduleUpdate = () => {
      if (frame) return;
      frame = requestAnimationFrame(updateFromScroll);
    };

    for (const { link } of entries) {
      link.addEventListener("click", () => {
        // The click target is authoritative while the browser performs its
        // anchor jump. Re-evaluate from geometry once scrolling has settled.
        clickLockUntil = performance.now() + 600;
        setActive(link);
        window.setTimeout(() => {
          clickLockUntil = 0;
          scheduleUpdate();
        }, 650);
      });
    }

    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate, { passive: true });
    window.addEventListener("hashchange", () => {
      const hashLink = linkForHash(window.location.hash);
      if (hashLink) {
        clickLockUntil = performance.now() + 300;
        setActive(hashLink);
        window.setTimeout(() => {
          clickLockUntil = 0;
          scheduleUpdate();
        }, 350);
      } else {
        scheduleUpdate();
      }
    });

    const initialHashLink = linkForHash(window.location.hash);
    if (initialHashLink) setActive(initialHashLink);
    else scheduleUpdate();
  };

  const applyDocsUi = () => {
    document.body.classList.toggle(
      "solo-home-page",
      Boolean(document.querySelector("[data-solo-home]"))
    );
    enhanceShellBlocks();
    setupCopyButtons();
    setupTocSync();
  };

  document.addEventListener("DOMContentLoaded", applyDocsUi);
  if (typeof document$ !== "undefined") document$.subscribe(applyDocsUi);
})();
