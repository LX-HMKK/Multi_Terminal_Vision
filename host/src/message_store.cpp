#include "message_store.h"

#include <QDateTime>
#include <QSqlQuery>
#include <QSqlError>
#include <QDebug>

MessageStore::MessageStore(const QString &dbPath)
    : m_dbPath(dbPath)
{
}

bool MessageStore::open()
{
    // 只在默认连接尚不存在时才 addDatabase，避免重复创建把旧连接关掉。
    if (QSqlDatabase::contains(QSqlDatabase::defaultConnection))
        m_db = QSqlDatabase::database();
    else
        m_db = QSqlDatabase::addDatabase("QSQLITE");
    m_db.setDatabaseName(m_dbPath);

    if (!m_db.open()) {
        qDebug() << "Database open error:" << m_db.lastError().text();
        return false;
    }

    QSqlQuery query;
    QString sql = "CREATE TABLE IF NOT EXISTS messages ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "message TEXT NOT NULL, "
                  "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);";
    if (!query.exec(sql)) {
        qDebug() << "Error creating table:" << query.lastError().text();
        return false;
    }
    qDebug() << "Table created successfully!";
    return true;
}

void MessageStore::storeMessage(const QString &path)
{
    QSqlQuery query;
    // 北京时间(UTC+8)
    QDateTime beijingTime = QDateTime::currentDateTimeUtc().addSecs(8 * 3600);
    QString timestamp = beijingTime.toString("yyyy-MM-dd HH:mm:ss");

    query.prepare("INSERT INTO messages (message, timestamp) VALUES (:message, :timestamp)");
    query.bindValue(":message", path);
    query.bindValue(":timestamp", timestamp);
    if (!query.exec())
        qDebug() << "Error inserting message:" << query.lastError().text();
    else
        qDebug() << "Message stored successfully!";
}

QList<QSqlRecord> MessageStore::all()
{
    QList<QSqlRecord> rows;
    QSqlQuery query;
    query.exec("SELECT id, message, timestamp FROM messages");
    while (query.next())
        rows.append(query.record());
    return rows;
}

bool MessageStore::addMessage(const QString &message)
{
    QSqlQuery query;
    query.prepare("INSERT INTO messages (message) VALUES (:message)");
    query.bindValue(":message", message);
    if (query.exec()) {
        qDebug() << "Message inserted successfully!";
        return true;
    }
    qDebug() << "Error inserting message:" << query.lastError().text();
    return false;
}

bool MessageStore::removeById(int id)
{
    QSqlQuery query;
    query.prepare("DELETE FROM messages WHERE id = :id");
    query.bindValue(":id", id);
    if (query.exec()) {
        qDebug() << "Message deleted successfully!";
        return true;
    }
    qDebug() << "Error deleting message:" << query.lastError().text();
    return false;
}

bool MessageStore::updateMessage(int id, const QString &message)
{
    // 保留原样：timestamp = CURRENT_TIMESTAMP（SQLite UTC）。
    QSqlQuery query;
    query.prepare("UPDATE messages SET message = :message, timestamp = CURRENT_TIMESTAMP WHERE id = :id");
    query.bindValue(":id", id);
    query.bindValue(":message", message);
    if (query.exec()) {
        qDebug() << "Message updated successfully!";
        return true;
    }
    qDebug() << "Error updating message:" << query.lastError().text();
    return false;
}
