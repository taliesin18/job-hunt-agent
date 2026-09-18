(() => {
  if (globalThis.__jobHuntExtractorInstalled) return;
  globalThis.__jobHuntExtractorInstalled = true;

  const EXCLUDED_SELECTORS = [
    "script", "style", "noscript", "svg", "nav", "footer", "[role='navigation']",
    "[class*='cookie' i]", "[id*='cookie' i]", "[class*='consent' i]", "[id*='consent' i]",
    "[class*='recommend' i]", "[id*='recommend' i]", "[class*='similar' i]", "[id*='similar' i]",
    "[class*='related' i]", "[id*='related' i]", "[class*='advert' i]", "[id*='advert' i]",
    "[class*='modal' i]", "[role='dialog']",
  ].join(",");

  function cleanText(value) {
    return String(value || "")
      .replace(/\u00a0/g, " ")
      .replace(/\r/g, "")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n[ \t]+/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function textFromHtml(value) {
    const container = document.createElement("div");
    container.innerHTML = String(value || "");
    return cleanText(container.innerText || container.textContent);
  }

  function textOf(selector, root = document) {
    for (const element of root.querySelectorAll(selector)) {
      const value = cleanText(element.innerText || element.textContent);
      if (value) return value;
    }
    return "";
  }

  function metaContent(...keys) {
    for (const key of keys) {
      const element = document.querySelector(
        `meta[property="${key}"], meta[name="${key}"], meta[itemprop="${key}"]`,
      );
      const value = cleanText(element?.content);
      if (value) return value;
    }
    return "";
  }

  function flattenJsonLd(value, found = []) {
    if (Array.isArray(value)) {
      value.forEach((item) => flattenJsonLd(item, found));
    } else if (value && typeof value === "object") {
      const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"]];
      if (types.some((type) => String(type).toLowerCase() === "jobposting")) found.push(value);
      if (value["@graph"]) flattenJsonLd(value["@graph"], found);
    }
    return found;
  }

  function jsonLdJob() {
    const jobs = [];
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        flattenJsonLd(JSON.parse(script.textContent || ""), jobs);
      } catch {
        // A malformed metadata block should not prevent visible-page extraction.
      }
    }
    return jobs[0] || null;
  }

  function asText(value) {
    if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(", ");
    if (value && typeof value === "object") return cleanText(value.name || value.value || "");
    return cleanText(value);
  }

  function formatLocation(value) {
    const locations = Array.isArray(value) ? value : [value];
    return locations.map((location) => {
      if (!location) return "";
      const address = location.address || location;
      if (typeof address === "string") return cleanText(address);
      return [address.addressLocality, address.addressRegion, address.addressCountry]
        .map(asText).filter(Boolean).join(", ");
    }).filter(Boolean).join("; ");
  }

  function formatSalary(value) {
    if (!value) return "";
    if (typeof value === "string") return cleanText(value);
    const amount = value.value?.value ?? value.value ?? value.minValue ?? "";
    const max = value.value?.maxValue ?? value.maxValue ?? "";
    const currency = asText(value.currency || value.value?.currency);
    const unit = asText(value.unitText || value.value?.unitText);
    const range = max && max !== amount ? `${amount}–${max}` : amount;
    return cleanText([currency, range, unit].filter(Boolean).join(" "));
  }

  function findContentRoot() {
    const selectors = [
      '[itemtype*="JobPosting"]',
      "article",
      "#job-details",
      "[data-automation*='job' i]",
      "[class*='job-description' i]",
      "[id*='job-description' i]",
      "main",
    ];
    for (const selector of selectors) {
      const candidate = document.querySelector(selector);
      if (candidate && cleanText(candidate.innerText || candidate.textContent).length > 120) return candidate;
    }
    return document.body;
  }

  function cleanedRootText(root) {
    const clone = root.cloneNode(true);
    clone.querySelectorAll(EXCLUDED_SELECTORS).forEach((node) => node.remove());
    return cleanText(clone.innerText || clone.textContent);
  }

  function sectionItems(root, headingPattern) {
    const headings = Array.from(root.querySelectorAll("h1,h2,h3,h4,h5,h6,strong,b"));
    for (const heading of headings) {
      if (!headingPattern.test(cleanText(heading.textContent))) continue;
      const items = [];
      let node = heading.nextElementSibling;
      while (node) {
        if (/^H[1-6]$/.test(node.tagName)) break;
        if (node.matches("ul,ol")) {
          node.querySelectorAll("li").forEach((item) => items.push(cleanText(item.innerText || item.textContent)));
        } else {
          const value = cleanText(node.innerText || node.textContent);
          if (value) items.push(value);
        }
        node = node.nextElementSibling;
      }
      const unique = [...new Set(items.filter(Boolean))];
      if (unique.length) return unique;
    }
    return [];
  }

  function labeledValue(text, labels) {
    for (const label of labels) {
      const match = text.match(new RegExp(`${label}\\s*[:\\-]\\s*([^\\n]+)`, "i"));
      if (match) return cleanText(match[1]);
    }
    return "";
  }

  function salaryFromText(text) {
    const match = text.match(/(?:[$€£]\s?\d[\d,.]*(?:\s*(?:-|–|to)\s*[$€£]?\s?\d[\d,.]*)?(?:\s*(?:per|\/)\s*(?:hour|year|month|day))?|\b(?:USD|EUR|GBP|PHP|AUD|CAD)\s?\d[\d,.]*(?:\s*(?:-|–|to)\s*\d[\d,.]*)?)/i);
    return cleanText(match?.[0]);
  }

  function deadlineFromText(text) {
    const match = text.match(/(?:apply by|application deadline|closing date|applications close)\s*[:\-]?\s*([^\n.]+)/i);
    return cleanText(match?.[1]);
  }

  function slug(value) {
    const result = cleanText(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    return result.slice(0, 48) || "posting";
  }

  function stableHash(value) {
    let hash = 2166136261;
    for (const character of value) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(36);
  }

  function extractJobPosting() {
    const structured = jsonLdJob();
    const root = findContentRoot();
    const pageText = cleanedRootText(root);
    const metadataDescription = textFromHtml(structured?.description);
    const rawDescription = metadataDescription.length > pageText.length ? metadataDescription : pageText;

    const title = asText(structured?.title) || textOf([
      "[data-automation='job-detail-title']",
      "[itemprop='title']",
      "h1",
    ].join(",")) || metaContent("og:title");
    const company = asText(structured?.hiringOrganization) || textOf([
      "[itemprop='hiringOrganization']",
      "[data-company-name]",
      "[class*='company-name' i]",
      "[class*='companyName' i]",
      ".job-details-jobs-unified-top-card__company-name",
    ].join(","));
    const location = formatLocation(structured?.jobLocation) || textOf([
      "[itemprop='jobLocation']",
      "[data-automation*='location' i]",
      "[class*='job-location' i]",
      "[class*='location' i]",
    ].join(","));

    const requiredSkills = sectionItems(root, /requirements?|qualifications?|what you bring|must[- ]have|skills? required/i);
    const preferredSkills = sectionItems(root, /preferred|nice[- ]to[- ]have|bonus skills?|desired/i);
    const responsibilities = sectionItems(root, /responsibilit|what you('|’)ll do|the role|duties/i);
    const benefits = sectionItems(root, /benefits?|perks?|why join|what we offer/i);
    const applicationInstructions = sectionItems(root, /how to apply|application process|apply now/i);
    const today = new Date().toISOString().slice(0, 10);
    const url = window.location.href;

    return {
      id: `job_${today}_${slug(company || title)}_${stableHash(url)}`,
      company: company || "Unknown",
      title: title || "Unknown",
      url,
      date_saved: today,
      raw_description: rawDescription,
      required_skills: requiredSkills,
      location: location || null,
      employment_type: asText(structured?.employmentType) || labeledValue(pageText, ["employment type", "job type"]) || null,
      seniority: labeledValue(pageText, ["seniority", "experience level", "career level"]) || null,
      compensation: formatSalary(structured?.baseSalary) || labeledValue(pageText, ["salary", "compensation", "pay range"]) || salaryFromText(pageText) || null,
      application_deadline: asText(structured?.validThrough) || deadlineFromText(pageText) || null,
      responsibilities,
      qualifications: requiredSkills,
      preferred_skills: preferredSkills,
      benefits,
      application_instructions: applicationInstructions,
      captured_at: new Date().toISOString(),
      status: "saved",
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "extract-job-posting") return;
    try {
      const job = extractJobPosting();
      if (!job.raw_description) throw new Error("No job-description text was found on this page.");
      sendResponse({ ok: true, job });
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || "Couldn't extract this job posting." });
    }
  });
})();
