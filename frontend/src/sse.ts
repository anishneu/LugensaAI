/** Splits a server-sent-events stream into its events. An event is a block of lines ended by a blank line; lines that
 * start with ":" are comments (the server's keep-alives) and carry nothing. Its own module so tests can import it without Vite. */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
