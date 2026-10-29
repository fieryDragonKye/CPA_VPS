/**
 * 配置文件相关 API（/config.yaml）
 */

import { apiClient } from './client';
import { readConfigETag, writeConfigChange } from './configVersion';

export const configFileApi = {
  async fetchConfigSnapshot(): Promise<{ content: string; etag: string | undefined }> {
    const response = await apiClient.getRaw('/config.yaml', {
      responseType: 'text',
      headers: { Accept: 'application/yaml, text/yaml, text/plain' },
    });
    const data: unknown = response.data;
    return {
      content: typeof data === 'string' ? data : data == null ? '' : String(data),
      etag: readConfigETag(response.headers),
    };
  },

  async fetchConfigYaml(): Promise<string> {
    return (await configFileApi.fetchConfigSnapshot()).content;
  },

  async saveConfigYaml(content: string, etag?: string): Promise<void> {
    await writeConfigChange('put', '/config.yaml', content, etag, {
      'Content-Type': 'application/yaml',
      Accept: 'application/json, text/plain, */*',
    });
  },
};
