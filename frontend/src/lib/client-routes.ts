export function clientPortalUrl(clientId: string | number) {
  return `/clients/${clientId}/portal`;
}

export function clientAnalyticsUrl(clientId: string | number) {
  return `/clients/${clientId}/analytics`;
}

export function clientTemplatesUrl(clientId: string | number) {
  return `/clients/${clientId}/templates`;
}

export function clientTemplateNewUrl(clientId: string | number) {
  return `/clients/${clientId}/templates/new`;
}

export function clientTemplateEditUrl(clientId: string | number, templateId: string | number) {
  return `/clients/${clientId}/templates/new?templateId=${templateId}`;
}

export function clientDemoUrl(clientId: string | number) {
  return `/clients/${clientId}/notifications/demo`;
}
