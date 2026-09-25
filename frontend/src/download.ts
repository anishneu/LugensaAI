/** Saves text as a file through the browser's own download: nothing is uploaded anywhere. */
export function downloadText(filename: string, text: string, type = "text/markdown;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Opens the browser's print dialog for a finished HTML page, where "Save as PDF" is one of the destinations. The page is put in a
 * hidden frame in this one: nothing is uploaded, and no PDF library is involved. The frame is left until the next print. */
export function printHtml(html: string): void {
  document.getElementById("print-frame")?.remove();
  const frame = document.createElement("iframe");
  frame.id = "print-frame";
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  frame.onload = () => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
  };
  frame.srcdoc = html;
  document.body.appendChild(frame);
}
