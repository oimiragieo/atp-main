// Copyright 2025 ATP Project Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { io, Socket } from 'socket.io-client';

interface Notification {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success';
  title: string;
  message: string;
  timestamp: number;
}

interface WebSocketContextType {
  socket: Socket | null;
  connected: boolean;
  notifications: Notification[];
  clearNotification: (id: string) => void;
  clearAllNotifications: () => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};

interface WebSocketProviderProps {
  children: ReactNode;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ children }) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    // Initialize WebSocket connection
    const newSocket = io(process.env.REACT_APP_WS_URL || 'http://localhost:8000', {
      auth: {
        token: localStorage.getItem('atp_token'),
      },
    });

    newSocket.on('connect', () => {
      console.log('WebSocket connected');
      setConnected(true);
    });

    newSocket.on('disconnect', () => {
      console.log('WebSocket disconnected');
      setConnected(false);
    });

    // Listen for system notifications
    newSocket.on('notification', (notification: Notification) => {
      setNotifications(prev => [notification, ...prev].slice(0, 50)); // Keep last 50 notifications
    });

    // Listen for system health updates
    newSocket.on('health_update', (data: any) => {
      // Handle health updates
      console.log('Health update:', data);
    });

    // Listen for provider status changes
    newSocket.on('provider_status', (data: any) => {
      const notification: Notification = {
        id: `provider_${Date.now()}`,
        type: data.status === 'healthy' ? 'success' : 'warning',
        title: 'Provider Status Change',
        message: `Provider ${data.name} is now ${data.status}`,
        timestamp: Date.now(),
      };
      setNotifications(prev => [notification, ...prev].slice(0, 50));
    });

    // Listen for cluster events
    newSocket.on('cluster_event', (data: any) => {
      const notification: Notification = {
        id: `cluster_${Date.now()}`,
        type: data.type === 'error' ? 'error' : 'info',
        title: 'Cluster Event',
        message: data.message,
        timestamp: Date.now(),
      };
      setNotifications(prev => [notification, ...prev].slice(0, 50));
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, []);

  const clearNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const clearAllNotifications = () => {
    setNotifications([]);
  };

  const value = {
    socket,
    connected,
    notifications,
    clearNotification,
    clearAllNotifications,
  };

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
};