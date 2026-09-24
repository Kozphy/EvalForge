import { createClient } from '@blinkdotnew/sdk'

export const blink = createClient({
  projectId: import.meta.env.VITE_BLINK_PROJECT_ID || 'ai-download-guide-fy5ab9jl',
  publishableKey: import.meta.env.VITE_BLINK_PUBLISHABLE_KEY || 'blnk_pk_Dig176uhRvPHYtafdTPpo8zjSYNGb2UT',
  authRequired: false,
  auth: { mode: 'managed' },
})
