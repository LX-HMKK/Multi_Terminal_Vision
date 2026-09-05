#include "widget.h"
#include "ui_widget.h"
#include <QDir>
#include <QNetworkInterface>
#include <QFileDialog>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlError>
#include <QDebug>
#include <QListWidgetItem>
#include <QColor>
#include <QTableWidget>
#include <QRegularExpression>

Widget::~Widget()
{
    delete ui;
}

void Widget::is_ui_visiable(bool state)
{
    (void)state; // 预留：控制 UI 使能（当前未使用）
}

// 取本机局域网 IPv4，用于界面展示（绑定仍用 Any，见构造函数）
QHostAddress Widget::get_local_host_ip()
{
    foreach (const QHostAddress &address, QNetworkInterface::allAddresses()) {
        if (address.protocol() == QAbstractSocket::IPv4Protocol &&
            address != QHostAddress::Null &&
            address != QHostAddress::LocalHost &&
            !address.toString().startsWith("127.")) {
            return address;
        }
    }
    return QHostAddress::Any;
}

Widget::Widget(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Widget)
    , tcp_thread(nullptr)
    , udp_thread(nullptr)
{
    ui->setupUi(this);
    setWindowTitle("上位机（服务端）");

    QString udp_port = "8888";   // 运算端回传视频
    QString tcp_port = "9999";   // 运算端指令/事件

    // 默认保存目录（相对程序运行目录，自动创建）
    ui->lineEdit_path->setText("screenshots/");
    ui->line_ip_addr->setText(get_local_host_ip().toString());
    ui->line_udp_port->setText(udp_port);
    ui->line_tcp_port->setText(tcp_port);
    is_ui_visiable(false);

    // 监听所有网卡，保证回环(127.0.0.1)与局域网都能连上
    QHostAddress local_ip = QHostAddress::Any;

    tcp_thread = new Tcp_Thread(local_ip, tcp_port);
    connect(tcp_thread, &Tcp_Thread::signal_msg, this, &Widget::print_tcp_msg);

    udp_thread = new Udp_Thread(local_ip, udp_port);
    connect(udp_thread, &Udp_Thread::signal_img, this, &Widget::display_udp_frame);
    connect(udp_thread, &Udp_Thread::signal_img_saved, this, &Widget::on_img_saved);

    connect(this, &Widget::destroyed, this, &Widget::close_thread);

    tcp_thread->start();
    udp_thread->start();
    tcp_thread->stop();
    udp_thread->stop();   // 等点击“开启监听”后再工作
    ui->label_msg->setText("等待客户端连接...");

    initDatabase();

    connect(ui->selectBtn,   &QPushButton::clicked, this, &Widget::on_selectBtn_clicked);
    connect(ui->deleteButton,&QPushButton::clicked, this, &Widget::on_deleteButton_clicked);
    connect(ui->addButton,   &QPushButton::clicked, this, &Widget::on_addButton_clicked);
    connect(ui->changeButton,&QPushButton::clicked, this, &Widget::on_changeButton_clicked);
    connect(ui->open,        &QPushButton::clicked, this, &Widget::on_open_clicked);
    connect(ui->close,       &QPushButton::clicked, this, &Widget::on_close_clicked);
    connect(ui->openButton,  &QPushButton::clicked, this, &Widget::on_openButton_clicked);
    connect(ui->closeButton, &QPushButton::clicked, this, &Widget::on_closeButton_clicked);
    connect(ui->btn_send,    &QPushButton::clicked, this, &Widget::on_btn_send_clicked);
    connect(ui->btn_path_change, &QPushButton::clicked, this, &Widget::on_btn_path_change_clicked);
}

void Widget::initDatabase()
{
    QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE");
    db.setDatabaseName("messages.db");
    if (!db.open()) {
        qDebug() << "Database open error:" << db.lastError().text();
        return;
    }
    QSqlQuery query;
    QString sql = "CREATE TABLE IF NOT EXISTS messages ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                  "message TEXT NOT NULL, "
                  "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);";
    if (!query.exec(sql))
        qDebug() << "Error creating table:" << query.lastError().text();
    else
        qDebug() << "Table created successfully!";
}

void Widget::display_udp_frame()
{
    // 取出所有待显示帧（线程安全）
    while (udp_thread->has_frame()) {
        ui->label_frame->setPixmap(udp_thread->take_frame());
    }
    QString saved = udp_thread->take_save_result();
    if (!saved.isEmpty())
        ui->label_msg->append("已保存！" + saved);
}

void Widget::print_tcp_msg()
{
    while (tcp_thread->has_msg()) {
        QString msg = tcp_thread->take_msg();
        ui->label_msg->setTextColor(QColor::fromRgb(255, 0, 0));
        ui->label_msg->append("client: " + msg);
        ui->label_msg->setTextColor(QColor::fromRgb(0, 0, 0));

        // 收到 ID_<id>_start/end 事件 → 触发当前帧保存。
        // 安全：只用数字还原文件名，防止事件串注入路径分割符/`..` 造成任意写文件。
        static const QRegularExpression idRe(QStringLiteral("^ID_(\\d+)_(start|end)$"));
        const QRegularExpressionMatch m = idRe.match(msg);
        if (m.hasMatch()) {
            const QString trackId = m.captured(1);          // 仅取数字 ID
            const QString event = m.captured(2);            // start / end
            const QString current_time = QDateTime::currentDateTime().toString("MM-dd-hh-mm-ss");
            const QString dir = ui->lineEdit_path->text().trimmed();
            const QString file_name = "ID_" + trackId + "_" + event + "_" + current_time + ".jpg";
            const QString file_path = QDir::cleanPath(dir + file_name);
            qDebug() << "Generated file path:" << file_path;
            udp_thread->request_save(file_path);
        }

        if (!tcp_thread->connect_flag) {
            on_btn_open_clicked();
            ui->label_msg->setText("等待客户端连接...");
        }

        // 数据库记录改为记录“保存的图片路径”，见 on_img_saved
    }
}

void Widget::storeMessage(const QString &path)
{
    QSqlDatabase db = QSqlDatabase::database();
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

void Widget::close_thread()
{
    tcp_thread->go_on();
    tcp_thread->start_flag = false;
    tcp_thread->quit();
    tcp_thread->wait();
    if (tcp_thread->connect_flag) {
        tcp_thread->socket->abort();
        tcp_thread->server->close();
    }

    udp_thread->go_on();
    udp_thread->start_flag = false;
    udp_thread->quit();
    udp_thread->wait();
}

void Widget::on_btn_open_clicked()
{
    if (ui->btn_open->text().toUtf8() == "开启监听") {
        if (tcp_thread->connect_flag) {
            ui->btn_open->setText("关闭监听");
            is_ui_visiable(true);
            udp_thread->go_on();
            tcp_thread->go_on();
            udp_thread->recv_flag = true;
            tcp_thread->recv_flag = true;
        } else {
            ui->label_msg->append("无客户端连接！");
        }
    } else if (ui->btn_open->text().toUtf8() == "关闭监听") {
        ui->btn_open->setText("开启监听");
        udp_thread->recv_flag = false;
        tcp_thread->recv_flag = false;
        is_ui_visiable(false);
        udp_thread->stop();
        tcp_thread->stop();
        ui->label_msg->clear();
        ui->label_frame->clear();
    }
}

void Widget::on_img_saved(const QString &path)
{
    storeMessage(path);   // 记录保存的图片路径到数据库
}

void Widget::on_btn_path_change_clicked()
{
    QString dir = QFileDialog::getExistingDirectory(this, "请选择文件保存路径", ".");
    if (dir.isEmpty())
        return;
    ui->lineEdit_path->setText(dir + "/");
    QDir().mkpath(dir);
}

void Widget::on_selectBtn_clicked()
{
    QSqlDatabase db = QSqlDatabase::database();
    QSqlQuery query;
    query.exec("SELECT id, message, timestamp FROM messages");

    ui->tableWidget->setColumnCount(3);
    ui->tableWidget->setHorizontalHeaderLabels({"ID", "Message", "Timestamp"});
    ui->tableWidget->setRowCount(0);
    ui->tableWidget->verticalHeader()->setVisible(false);

    int row = 0;
    while (query.next()) {
        ui->tableWidget->insertRow(row);
        ui->tableWidget->setItem(row, 0, new QTableWidgetItem(query.value("id").toString()));
        ui->tableWidget->setItem(row, 1, new QTableWidgetItem(query.value("message").toString()));
        ui->tableWidget->setItem(row, 2, new QTableWidgetItem(query.value("timestamp").toString()));
        row++;
    }
}

void Widget::on_deleteButton_clicked()
{
    QString id = ui->lineEdit1->text().trimmed();
    if (id.isEmpty()) { ui->label_msg->setText("ID is empty!"); return; }

    QSqlDatabase db = QSqlDatabase::database();
    QSqlQuery query;
    query.prepare("DELETE FROM messages WHERE id = :id");
    query.bindValue(":id", id.toInt());
    if (!query.exec()) {
        qDebug() << "Error deleting message:" << query.lastError().text();
        ui->label_msg->setText("Error deleting message!");
    } else {
        ui->label_msg->setText("Message deleted successfully!");
    }
}

void Widget::on_addButton_clicked()
{
    QString message = ui->lineEdit2->text().trimmed();
    if (message.isEmpty()) { ui->label_msg->setText("Message is empty!"); return; }

    QSqlDatabase db = QSqlDatabase::database();
    QSqlQuery query;
    query.prepare("INSERT INTO messages (message) VALUES (:message)");
    query.bindValue(":message", message);
    if (!query.exec()) {
        qDebug() << "Error inserting message:" << query.lastError().text();
        ui->label_msg->setText("Error inserting message!");
    } else {
        ui->label_msg->setText("Message inserted successfully!");
    }
    ui->lineEdit2->clear();
}

void Widget::on_changeButton_clicked()
{
    QString id = ui->lineEdit4->text().trimmed();
    QString message = ui->lineEdit3->text().trimmed();
    if (id.isEmpty() || message.isEmpty()) {
        ui->label_msg->setText("ID or Message is empty!");
        return;
    }

    QSqlDatabase db = QSqlDatabase::database();
    QSqlQuery query;
    query.prepare("UPDATE messages SET message = :message, timestamp = CURRENT_TIMESTAMP WHERE id = :id");
    query.bindValue(":id", id.toInt());
    query.bindValue(":message", message);
    if (!query.exec()) {
        qDebug() << "Error updating message:" << query.lastError().text();
        ui->label_msg->setText("Error updating message!");
    } else {
        ui->label_msg->setText("Message updated successfully!");
    }
    ui->lineEdit3->clear();
    ui->lineEdit4->clear();
}

void Widget::on_open_clicked()       { send_message("0"); }
void Widget::on_close_clicked()      { send_message("1"); }
void Widget::on_openButton_clicked() { send_message("2"); }
void Widget::on_closeButton_clicked(){ send_message("3"); }

void Widget::send_message(const QString &msg)
{
    // 统一以换行结尾（接收端按行分帧）
    if (tcp_thread->connect_flag) {
        tcp_thread->socket->write((msg + "\n").toUtf8());
        tcp_thread->socket->flush();
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 255));
        ui->label_msg_send->append("server: " + msg);
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 0));
    } else {
        qDebug() << "Not connected to the client!";
        ui->label_msg->setText("Not connected to the client!");
    }
}

void Widget::on_btn_send_clicked()
{
    QString msg = ui->textEdit_send->toPlainText().trimmed();
    if (!msg.isEmpty() && tcp_thread->socket &&
        tcp_thread->socket->state() == QTcpSocket::ConnectedState) {
        tcp_thread->socket->write((msg + "\n").toUtf8());
        tcp_thread->socket->flush();
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 255));
        ui->label_msg_send->append("server: " + msg);
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 0));
        ui->textEdit_send->clear();
    }
}
