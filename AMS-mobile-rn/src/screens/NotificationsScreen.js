import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import { getNotifications } from '../api/ams';
import { useSession } from '../state/session';

export default function NotificationsScreen() {
  const { accessToken } = useSession();
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await getNotifications({ token: accessToken });
      setItems(res?.notifications || []);
    } catch (e) {
      setError(e?.message || 'Failed');
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      <View className="bg-mit-purple px-5 pt-14 pb-6">
        <Text className="text-white text-2xl font-extrabold">Notifications</Text>
        <Text className="text-white/80 text-xs mt-1">All updates</Text>
        <TouchableOpacity onPress={load} className="mt-4 bg-white/10 px-4 py-2 rounded-xl">
          <Text className="text-white font-bold text-xs">Refresh</Text>
        </TouchableOpacity>
      </View>

      <View className="px-5 -mt-4 pb-10">
        {error ? (
          <View className="bg-red-50 border border-red-100 rounded-2xl p-4 mt-4">
            <Text className="text-red-700 font-bold">{error}</Text>
          </View>
        ) : null}

        <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
          {items.length === 0 ? (
            <Text className="text-slate-500 text-xs">No notifications</Text>
          ) : (
            <View>
              {items.slice(0, 50).map((n) => (
                <View key={String(n.id)} className="py-3 border-b border-slate-100">
                  <View className="flex-row justify-between">
                    <Text className="text-slate-900 font-bold">{n.title}</Text>
                    <Text className={`text-xs font-extrabold ${n.is_read ? 'text-slate-400' : 'text-mit-teal'}`}>
                      {n.is_read ? 'READ' : 'NEW'}
                    </Text>
                  </View>
                  <Text className="text-slate-500 text-xs mt-1">{n.message}</Text>
                  {n.timestamp ? (
                    <Text className="text-slate-400 text-[10px] mt-1">{n.timestamp}</Text>
                  ) : null}
                </View>
              ))}
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
}
