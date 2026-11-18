// Test cases for rules.yml (semgrep scan --test .semgrep). Never compiled or bundled.
export function Bad({ html, code }: { html: string; code: string }) {
  // ruleid: pap-js-eval
  eval(code);
  // ruleid: pap-js-eval
  const f = new Function(code);
  // ruleid: pap-token-in-browser-storage
  localStorage.setItem("token", code);
  // ruleid: pap-react-dangerous-html
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Good({ text }: { text: string }) {
  // ok: pap-react-dangerous-html
  return <div>{text}</div>;
}
