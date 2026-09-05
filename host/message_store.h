#ifndef MESSAGE_STORE_H
#define MESSAGE_STORE_H

#include <QSqlDatabase>
#include <QSqlRecord>
#include <QList>

// SQLite 消息存取。把原来 Widget 里的数据库 CRUD 收敛到独立的非 Q_OBJECT 类，
// 让 Widget 只专注 UI / 网络 / 存图路由，破除 God 类。
//
// 语义完全还原原 widget.cpp：
//   - storeMessage   写“北京时间”字符串
//   - updateMessage  用 CURRENT_TIMESTAMP（SQLite UTC）——这是原代码的既有时区不一致，
//                     此处刻意保留，见 docs/known-issues.md
class MessageStore
{
public:
    explicit MessageStore(const QString &dbPath = "messages.db");

    // 打开（或复用）默认连接并建表；重复调用安全（避免重复 addDatabase 触发
    // "duplicate connection name" 警告并关掉旧默认连接）。
    bool open();

    void storeMessage(const QString &path);          // 记录保存的图片路径（北京时间）
    QList<QSqlRecord> all();                          // 全部记录：id / message / timestamp
    bool addMessage(const QString &message);          // 新增记录（timestamp 走 DB 默认）
    bool removeById(int id);                          // 删除记录
    bool updateMessage(int id, const QString &message);  // 修改记录（timestamp = CURRENT_TIMESTAMP）

private:
    QString m_dbPath;
    QSqlDatabase m_db;
};

#endif // MESSAGE_STORE_H
