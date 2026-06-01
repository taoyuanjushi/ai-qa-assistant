import './App.css'
import ChatPage from './ChatPage'

// 应用根组件：当前 MVP 只有一个聊天页面。
function App() {
  // 这里直接返回聊天页面，后续如果增加路由或布局，可以从这个组件扩展。
  return <ChatPage />
}

export default App
