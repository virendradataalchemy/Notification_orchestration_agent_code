export function clientPortalUrl(clientPath: string | number) {
  return `/clients/${clientPath}/portal`;
}

export function clientAnalyticsUrl(clientPath: string | number) {
  return `/clients/${clientPath}/analytics`;
}

export function clientTemplatesUrl(clientPath: string | number) {
  return `/clients/${clientPath}/templates`;
}

export function clientTemplateNewUrl(clientPath: string | number) {
  return `/clients/${clientPath}/templates/new`;
}

export function clientTemplateEditUrl(clientPath: string | number, templateId: string | number) {
  return `/clients/${clientPath}/templates/new?templateId=${templateId}`;
}

export function clientDemoUrl(clientPath: string | number) {
  return `/clients/${clientPath}/notifications/demo`;
}
