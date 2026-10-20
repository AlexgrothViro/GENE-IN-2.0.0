export function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
  return node;
}

export function clearChildren(node) {
  if (typeof node.replaceChildren === "function") {
    node.replaceChildren();
  } else {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  return node;
}

export function replaceContent(node, ...children) {
  clearChildren(node);
  children.forEach((child) => {
    if (child != null) node.append(child);
  });
  return node;
}

export function createElement(doc, tag, props = {}, children = []) {
  const node = doc.createElement(tag);
  Object.entries(props).forEach(([key, value]) => {
    if (value == null) return;
    if (key === "text") node.textContent = String(value);
    else if (key === "class") node.className = String(value);
    else if (key === "dataset") {
      Object.entries(value).forEach(([dataKey, dataValue]) => {
        node.dataset[dataKey] = String(dataValue);
      });
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, String(value));
  });
  (Array.isArray(children) ? children : [children]).forEach((child) => {
    if (child == null) return;
    node.append(typeof child === "object" ? child : doc.createTextNode(String(child)));
  });
  return node;
}
