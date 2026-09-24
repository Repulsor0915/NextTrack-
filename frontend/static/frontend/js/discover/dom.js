export function collectElements(ids) {
  return Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));
}

export function make(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}
