# ORBIT brand application

Version 0.13.1, 11 November 2026. Applied from the user-supplied Constellation / Mission Control brand board.

| Token | Value | Application |
| --- | --- | --- |
| Navy | `#111D2E` | Main canvas and identity background |
| Cyan | `#69D9FD` | Constellation ring, active navigation, links and focus/framing |
| Amber | `#FFB64C` | Top constellation node, primary actions and headline emphasis |
| Paper | `#F7F5F0` | Wordmark, nodes and primary type |
| Teal | `#17616F` | Secondary surfaces and status treatments |

The constellation symbol is a cyan ring with five evenly spaced nodes: one amber at the top and four paper nodes. Scalable SVG assets were recreated from the supplied image reference; original editable logo/font files were not supplied. The application lockup combines that mark with ORBIT and “by Pentagon Solutions”. It appears in welcome, navigation, loading and footer branding; the symbol is also the favicon and decorative overview motif.

Headline: **Make project data consistent.**

Supporting line: **Built with AI. Grounded in project delivery.**

The app retains its working connection/mapping actions rather than adding a non-functional campaign booking button. This branding update does not add AI execution capabilities or change connector permissions.

Reusable source assets are in `frontend/public/brand/`: the normal mark, a light-background mark and a paper monochrome mark. UI lockup code is in `frontend/src/Brand.tsx`; palette and derived surface colours are scoped in `frontend/src/portal.css`. Light/monochrome assets are available for future documents; a light-mode switch is not introduced by this change.

Screenshots in `docs/images/` use an isolated browser fixture with test-entered names, not customer data or seeded product content.

[Branded welcome preview](images/brand-welcome.png) · [Branded connection hub](images/connection-hub.png)
