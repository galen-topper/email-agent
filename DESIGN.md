# AgentMail Design System

## Visual Theme

### Color Palette
- **Background Primary**: `#000000` (Pure Black)
- **Background Secondary**: `#1a1a1a` (Dark Gray)
- **Background Tertiary**: `#2a2a2a` (Medium Gray)
- **Text Primary**: `#ffffff` (White)
- **Text Secondary**: `#b3b3b3` (Light Gray)
- **Accent**: `#3b82f6` (Blue) - Used for CTAs, active states, links
- **Success**: `#10b981` (Green) - "Needs Reply" badge
- **Danger**: `#ef4444` (Red) - High priority indicator
- **Warning**: `#f59e0b` (Orange) - Spam indicator

## Layout Structure

### Header (Sticky)
- **Logo**: "Agent**Mail**" with blue accent on "Mail"
- **Stats Bar**: Shows email count, replies needed, drafts pending
- **Fetch Button**: Primary action button to pull new emails

### Sidebar (240px fixed width)
Navigation organized into two sections:

**Views:**
- 📥 All Mail (default active)
- ✉️ Needs Reply
- ⚡ High Priority

**Filters:**
- 📬 Normal
- 📭 Low Priority
- 🗑️ Spam

### Main Content Area

**Toolbar:**
- Search box with icon (filters emails in real-time)

**Email List:**
Each email item displays:
- **Priority Indicator**: 3px left border (red/blue/gray)
- **From Address**: Bold white text
- **Time**: Relative time (e.g., "2h ago")
- **Subject**: Medium weight
- **Snippet**: Truncated preview text
- **Badges**: Priority, spam status, action needed

**Hover States:**
- Background changes to `#1a1a1a` on hover
- Smooth 0.15s transitions

### Modal Email Viewer

**Header:**
- Email subject as title
- Close button (×) in top right

**Body:**
- **Metadata Box**: From, To, Date in styled container
- **AI Summary Section**: With blue left border accent
- **Email Content**: Original message text
- **Suggested Replies**: Draft options with Send/Edit buttons

## Typography

- **Font Family**: System font stack (Apple, Segoe, Roboto)
- **Logo**: 24px, 700 weight, -0.5px letter spacing
- **Email Subject**: 14px, 400-600 weight
- **Body Text**: 13px, 400 weight
- **Section Titles**: 11-14px, 600 weight, uppercase, 0.5px letter spacing

## Interactive Elements

### Buttons
- **Default**: Dark gray background, white text, border
- **Primary**: Blue background, white text
- **Hover**: Lighter shade, blue border on default buttons
- **Border Radius**: 6-8px for modern look

### Badges
- **Small**: 11px uppercase text
- **Rounded**: 4px border radius
- **Translucent backgrounds** with colored borders
- Priority-specific colors (red/blue/gray/orange)

## Animations

- **Transitions**: 0.15s ease on all interactive elements
- **Spinner**: Rotating border animation for loading states
- **Smooth scrolling** with custom dark-themed scrollbars

## Responsive Design

- **Minimum width**: 1024px recommended
- **Scrollable areas**: Email list and modal content
- **Fixed elements**: Header, sidebar, toolbar

## Key Design Principles

1. **High Contrast**: Pure black (#000) with white text for maximum readability
2. **Subtle Hierarchy**: Gray variations create depth without heavy borders
3. **Accent-Driven**: Blue accent guides user attention to key actions
4. **Gmail-Inspired**: Familiar patterns (sidebar, list, badges) with unique dark aesthetic
5. **Information Density**: Compact but readable layout showing maximum emails
6. **Visual Feedback**: Clear hover states, active indicators, loading spinners

## File Structure

```
src/
├── templates/
│   └── index.html          # Main HTML structure
├── static/
    ├── style.css           # Complete CSS styling
    └── app.js              # Frontend JavaScript logic
```

## Future Enhancements

- Dark/light theme toggle
- Customizable accent colors
- Compact/comfortable/spacious density options
- Keyboard shortcuts overlay
- Drag-and-drop email organization
