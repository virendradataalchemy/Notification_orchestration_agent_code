export function clientPortalUrl(clientPath: string | number) {
  return `/clients/${clientPath}/portal`;
}

export function clientAnalyticsUrl(clientPath: string | number) {
  return `/client/${clientPath}/analytics`;
}

export function clientDepartmentsUrl(clientPath: string | number) {
  return `/client/${clientPath}/departments`;
}

export function clientDepartmentUrl(clientPath: string | number, department: string) {
  return `/client/${clientPath}/departments/${department}`;
}

export function clientTemplatesUrl(clientPath: string | number) {
  return `/client/${clientPath}/templates`;
}

export function clientTemplateNewUrl(clientPath: string | number) {
  return `/client/${clientPath}/templates/new`;
}

export function clientTemplateEditUrl(clientPath: string | number, templateId: string | number) {
  return `/client/${clientPath}/templates/new?templateId=${templateId}`;
}

export function clientDemoUrl(clientPath: string | number) {
  return `/client/${clientPath}/send-demo`;
}

export function clientSettingsUrl(clientPath: string | number) {
  return `/clients/${clientPath}/settings`;
}
