import { Platform } from 'react-native';

export const STUDENT_EMAIL_DOMAIN = '@school.mituniversity.edu.in';

// API base URL
// - Android emulator reaches host machine via 10.0.2.2
// - Default assumes Flask/Gunicorn is reachable on port 5000
// - If you're using Docker Compose + Nginx (port 80), set EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2
// - If you're on a physical device, use your PC LAN IP (e.g., http://192.168.1.5:5000)
const override = process.env.EXPO_PUBLIC_API_BASE_URL;

export const API_BASE_URL =
  override ||
  (Platform.OS === 'android'
    ? 'http://10.0.2.2:5000'
    : Platform.OS === 'web'
      ? 'http://localhost:5000'
      : 'http://localhost:5000');
