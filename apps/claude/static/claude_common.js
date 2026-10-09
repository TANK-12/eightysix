/* Shared by the Claude app's pages: the classic page (app.js), the Enjoy
 * layout (enjoy.js) and Docs. The API helpers, markdown-lite, and the drawing
 * of a conversation's events now live in /shared/forge_convo.js (Mission
 * Control draws chats with the same code); load that first. ClaudeCommon is
 * the same object under the name these pages already use:
 *
 *   ClaudeCommon.draw(event, view, { shown(view), scroll(view, force),
 *                                    init(event), browserTool(card),
 *                                    assistant(message, view) })
 *   ClaudeCommon.newView(id)   an empty view for one conversation
 *   ClaudeCommon.onStatus      where a page's status messages go
 */
window.ClaudeCommon = window.ForgeConvo;
